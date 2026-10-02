# RUNNER_MINIMI_CORREZIONI - correzioni dopo la verifica di RUNNER_MINIMI_CHIUSURE (02/10/2026)

**STATO AL 02/10, punto 11.**
- **Fatto**: punti 1-3 e 5-11 committati (codice `2081711`). I test mirati del punto 11
  sono verdi.
- **Manca**:
  - l'esito della falsificazione finale (in corso);
  - rigenerare `RUNNER_MINIMI_CORREZIONI.patch` da `git diff 67261b9`.
- **Chi riprende**: `git log verifica-runner`.

Correttore: delegato Opus. Worktree `agent-a0274ee823e0cae47`, ramo locale `verifica-runner`
(sopra `42984d2` = patch del runner del 01/10 applicata su `master` `67261b9`).
Niente commit su master, niente push, mai `git add -A`. Nessun ordine vero, nessun replay.

Consegna:
- `RUNNER_MINIMI_CORREZIONI.patch`
  - contenuto: `git diff master HEAD -- Betfair`, cioè la patch COMPLETA (runner del
    01/10 + correzioni), 43 file, file nuovi compresi, fine riga LF;
  - verifica: applicata con `git apply --3way` su un ramo da `master`
    (`prova-patch-correzioni-2`), riproduce l'albero di `verifica-runner` con diff
    `-- Betfair` vuoto;
  - attenzione: va applicata così com'è (LF). La copia CRLF del checkout fallisce, come il
    01/10.
- `falsifica_runner_correzioni.py` e `falsifica_runner_correzioni_out.txt`: 23 mutazioni
  nuove, le 8 del delegato e le 15 della verifica.
- Questo referto.
- Gli artefatti della verifica del mattino (`VERIFICA_RUNNER_MINIMI.md`, sonde) restano
  nella cartella.

Commit locali sul ramo, sopra `42984d2`:

| commit | contenuto |
|---|---|
| `01ed6a7` | punti 1, 2, 3, 5, 6, 7, 8, 10 |
| `7b71549` | punto 9, test nuovi, commenti |
| `7738c1f` | lookup per bet del tennis |
| `6680303` | eventi del cancel tradotto |
| `7e34f3c` | test di tolleranza, chiude R9 (ultimo commit) |

## 0. Esito in breve

| punto | stato |
|---|---|
| 1 paper = live | **FATTO** |
| 2 codice del rifiuto su ogni strada | **FATTO** |
| 3 cancel/replace su ordine tradotto | **FATTO** |
| 4 equivalente su coda e REST di Safe | **NON FATTO, fermato e riportato** (§4): richiede di toccare la riconciliazione e il regolamento dei bot |
| 5 mercati a 3+ esiti | **FATTO**: il buco R8 è chiuso |
| 6 parcheggio della banca in banda | **FATTO** |
| 7 guardie mancanti | **FATTO** |
| 8 test indeboliti, xfail, commenti | **FATTO** |
| 9 doppia chiusura | **PARZIALE** |
| 10 reperto 3 | **FATTO** nel perimetro del runner |

Dettaglio del punto 9:
- corretta nel runner (green-up di mercato);
- **due difetti money-critical nei bot (Safe e Omega) riportati e NON toccati** (§9).

Dettaglio del punto 10:
- un solo CRITICAL per episodio, mai una chiamata a Betfair;
- la condotta dei bot (ritenti illimitati) è riportata.

**Test mirati** (export isolato, §11):
- file toccati: **1244 passed, 3 failed, 2 skipped, 8 xfailed**. I 3 rossi sono preesistenti
  e dipendono dall'ordine: identici sulla base `master`;
- 117 file collegati non toccati: **2444 passed, 8 failed**. Gli 8 sono identici sulla base
  e dipendono dall'ambiente: nell'export mancano `migrations/` e `frontend/`. Nel worktree
  quei 5 file danno **147 passed**.

**Falsificazione** (`falsifica_runner_correzioni_out.txt`, export di `7e34f3c`, set di 16 file e
905 test): **46 mutazioni su 46 ROSSE, nessuna sopravvissuta**.
- **23 nuove** (C1-C23, almeno una per ogni correzione).
- **Le 8 del delegato** (M1-M8). L'ancora di M4 è aggiornata perché il blocco è cambiato.
- **Le 15 della verifica del mattino** (R1-R15). R3 è riscritta sulla nuova quota di
  parcheggio.
  - **R8**, che sopravviveva, ora è rossa (`test_p5_tre_esiti_mai_equivalente`).
  - **R9**, che sopravviveva, ora è rossa (`test_p5_equivalente_peggiore_oltre_la_tolleranza_mai_usato`).

Ripristino byte per byte: suite uguale alla base. L'unico rosso della base è
`test_l03_stats_azzerate_a_bot_fermo`, preesistente e dipendente dall'ordine: è rosso anche
su `master` e sulla patch del 01/10.

## 1. Paper = specchio del live

- **Prima**:
  - `live_order_worker._costruisci_chiusura` costruiva la gamba di greenup/cash-out sotto il
    minimo DIRETTA in paper (`build_order(simulato_ammette_sotto_minimo=not live)`), anche
    sotto 0,50: era il take-profit di Omega da 0,28;
  - `_place_closing_leg` andava al place-and-trim solo se `_is_live_mode(mode)`.
- **Dopo**:
  - `live_order_worker.py:2106` (`_place_closing_leg`): `sotto_minimo` non dipende più dal
    modo; in paper parte la STESSA sequenza place-and-trim sul client della riga
    (`client=`), e sotto 0,50 lo stesso rifiuto (`_place_sub_minimum` →
    `verifica_importo_finale`);
  - `live_order_worker.py:2178` (`_costruisci_chiusura`): stessa decisione in ogni modo
    (`del mode`);
  - `live_order_build.build_order`: tolto il parametro `simulato_ammette_sotto_minimo` e il
    suo ramo.
- **Il client simulato sa fare il place-and-trim?** Sì, verificato nel codice di flumine
  2.x del `.venv`:
  - `simulation/simulatedorder.py:286-305`: `cancel` con `update_data["size_reduction"]`
    (cancel parziale);
  - `execution/simulatedexecution.py:104-140`: `execute_replace`;
  - in paper le chiamate vanno in un thread pool con le latenze (place = bet delay +
    0,12 s, replace = bet delay + 0,28 s), dentro il timeout della sequenza sincrona
    (`_submin_timeout_sec`, 20 s);
  - la macchina asincrona del motore lo usa già in paper
    (`test_place_and_trim_ogni_passo_sul_client_della_modalita[paper]`).
- **Il motore** (`_applica_minimi`) non guarda il modo, quindi paper e live hanno lo stesso
  verdetto (era già così).
- **Test**:
  - `test_runner_minimi_correzioni_2026_10_02.py::test_p1_stesso_ordine_043_in_paper_e_in_live_stesso_mandato_e_stesso_evento`:
    0,43 @18 dà in entrambi i modi punta Under 7,31 @1,06 mandata e lo stesso evento al bot;
  - `::test_p1_build_order_senza_via_simulata_e_mai_sotto_il_minimo`;
  - `::test_p1_gamba_di_chiusura_paper_sotto_minimo_mai_costruita_diretta`;
  - `test_cashout_pro_2026_09_10.py::test_closing_leg_in_paper_stessa_decisione_del_live`.
    È **condotta cambiata per decisione dell'utente**: sostituisce
    `test_closing_leg_in_paper_non_usa_il_trucco`, che codificava il paper più generoso del
    live (catalogo §7 n. 14).
- **Falsificazione**: C1, C2, R12.
- **Da sapere**: un green-up sotto il minimo eseguito DAL MOTORE (azione `greenup` sul
  canale) gira la sequenza sincrona sul thread del motore, fino a circa 20 s di attesa.
  - In live era già così con la patch del 01/10; ora vale anche in paper.
  - È lo stesso compromesso del worker. Non l'ho cambiato (la macchina asincrona c'è solo per
    `place`): da valutare.

## 2. Codice del rifiuto su ogni strada

- **Prima**: l'evento `order` era costruito da `riga_specchio_da_esito`, che ha SOLO le
  chiavi `CHIAVI_SPECCHIO`, quindi nessun codice:
  - sulla strada asincrona (aggancio al volo: `motore_ordini.py` `avanza_aggancio` →
    `_esegui(errore_forzato=...)`);
  - sugli errori del dispatch;
  - sul place-and-trim abortito c'era solo `errore`.
  La riga della coda aveva solo il testo `error`.
- **Dopo**:
  - `motore_ordini.py:610` `codice_errore(testo)`: prima i codici noti in qualunque punto
    del testo (`SOTTO_MINIMO_NON_PIAZZABILE`, `SUBMIN_PARCHEGGIO_ABBINABILE`,
    `INVALID_PROFIT_RATIO_PREVISTO`, `INVALID_BET_SIZE`), poi il prefisso `codice:` con
    `_` (i `M_*` del motore, `post_place`);
  - `:632` `_estremi_errore` → `error_code` + `errore`;
  - `_esegui` (`:1534`) li aggiunge a ogni evento non riuscito: aggancio, dispatch, guardie
    rifatte;
  - il place-and-trim abortito (`_chiudi_submin`) ha `error_code` oltre a `errore`;
  - il rifiuto di taglia (`_emetti_rifiuto_taglia`) ha `error_code="INVALID_BET_SIZE"`;
  - la coda: `live_order_worker.py:1194` `result["error_code"]` sulla riga `error`.
- **Nomi**: `errore` era già nel repo (evento del place-and-trim abortito); `error_code` è il
  nome di Safe (`PlaceOutcome.error_code`), di Mike (`_esito_rifiuto_mercato(error_code=)`) e
  di Omega (`PlaceRifiutato.error_code`).
- **Perché NON in `CHIAVI_SPECCHIO`**: sono le colonne di `betfair_live_orders`, e il test
  `test_porta_banco_f4::test_eventi_con_le_chiavi_dello_specchio_di_produzione` le confronta
  con `LiveTradingStrategy._order_row`. Le chiavi d'errore viaggiano solo nell'evento, come
  `submin_step` e `portata_al_minimo`.
- **L'ack sincrono** resta con le sue 5 chiavi (contratto `CHIAVI_ACK`): il codice è il
  prefisso del `motivo`.
- **Test**:
  - `test_p2_codice_dal_testo` (7 casi);
  - `test_p2_strada_sincrona_ack_col_codice`;
  - `test_p2_strada_asincrona_aggancio_evento_col_codice` (freno tirato durante l'attesa:
    `error_code=kill_switch`);
  - `test_p2_strada_asincrona_sotto_minimo_dopo_l_aggancio`;
  - `test_p2_errore_del_dispatch_evento_col_codice`;
  - `test_p2_strada_della_coda_result_col_codice`.
- **Falsificazione**: C3, C4, C5.
- **Nota**: sul canale una banca sotto il minimo su un mercato NON ancora seguito viene
  rifiutata in modo sincrono, perché senza book non si sa se il mercato ha due esiti. Non va
  in aggancio. Una chiusura sta sempre su un mercato seguito, ma va saputo.

## 3. Cancel e replace su un ordine tradotto

- **Prima**: il bot aveva il `bet_id` VERO (punta Under 7,31 @1,06). Un cancel parziale
  «0,20» riduceva la punta di 0,20 (invece di 3,40). Un replace a 17 spostava la punta Under
  a 17.
- **Dopo** (`motore_ordini.py:1193` `_traduci_annullo`, chiamato da `_controlla` per
  `cancel` e `replace`):
  - il motore lega il `bet_id` vero al comando tradotto (`_bet_tradotti`, `:1891`, mentre
    emette l'evento);
  - **cancel totale**: annulla l'ordine vero;
  - **cancel con `size_reduction` r** (termini del chiesto): riduzione vera
    `r × mandata/chiesta` al centesimo (banca Over S@q, fattore q−1). Se il residuo vero
    scende sotto 0,50 o esce dalla banda `INVALID_PROFIT_RATIO`, rifiuto
    `SOTTO_MINIMO_NON_PIAZZABILE` col residuo nei termini chiesti, nessun cancel. Se r copre
    tutto, cancel totale;
  - **replace a `new_price`**: diventa un cancel TOTALE dell'ordine vero. A cancel
    CONFERMATO (`avanza_riprezzi`, `:2034`: ordine vero terminale) parte un nuovo place
    dell'ordine CHIESTO alla quota nuova, per la parte annullata. La parte annullata è il
    resto al cancel meno ciò che si è abbinato nel frattempo, riportata nei termini chiesti.
    Il nuovo place passa da un verdetto dei minimi nuovo (`_applica_minimi`) con lo stesso
    ref del bot. Mai un replace dell'ordine vero. Mai il nuovo ordine prima della conferma
    del cancel: niente doppia esposizione. Oltre 20 s senza conferma: evento `rifiutato`
    `REPLACE_TRADOTTO_CANCEL_NON_CONFERMATO`;
  - **eventi del cancel/replace nei termini del chiesto**: `piano["tradotto"]`, altrimenti
    il bot riceveva la riga della punta Under;
  - **lookup per bet anche col runner tennis** (`_ordine_per_bet`, `:1171`).
- **Strade**: il canale (Safe `porta_ordini` espone `cancel`/`replace`, `porta_ordini.py:89`;
  Mike, Omega e desktop passano dallo stesso `_controlla`). La coda e il REST non traducono
  mai (§4), quindi non hanno ordini tradotti.
- **Test** (tutti col bot Safe sul canale VERO):
  - `test_p3_cancel_totale_annulla_l_ordine_vero` (con l'evento del cancel in termini Over);
  - `test_p3_cancel_parziale_convertito_nei_termini_del_vero` (0,10 → 1,70, resta 5,61);
  - `test_p3_cancel_parziale_che_lascerebbe_sotto_050_rifiutato_col_residuo`;
  - `test_p3_cancel_su_ordine_non_tradotto_invariato`;
  - `test_p3_replace_su_tradotto_cancel_poi_nuovo_verdetto_mai_la_quota_dell_over` (banca
    0,43 @17 → punta Under 6,88 @1,07);
  - `test_p3_replace_su_tradotto_non_ripiazza_prima_del_cancel_confermato`.
- **Falsificazione**: C6, C7, C8, C9, C23.

## 4. Equivalente anche su coda e REST di Safe: NON FATTO (fermato, da decidere)

Ho letto il codice (anche con un sotto-agente in sola lettura) e mi fermo: farlo tocca la
**riconciliazione e il regolamento dei bot**, cioè fuori dal perimetro e con rischio sui
soldi.

- **Coda**: Safe conferma le righe dalla riga di coda e dallo SPECCHIO `betfair_live_orders`
  (`omega_service._mirror_fill` :3450-3475 → `_flumine_confirm`). Lo specchio porta
  l'ordine VERO, e una traduzione nel worker scriverebbe sulla riga Over lay 0,43 i numeri
  della punta Under 7,31 @1,06 (esposizione sbagliata). Per farla servirebbe:
  - riportare lo specchio nei termini del chiesto (ma lo specchio deve restare veritiero per
    l'interfaccia e per la riconciliazione col conto);
  - oppure insegnare la traduzione a `_mirror_fill`, cioè codice dei bot.
- **REST**: la chiusura tradotta va confermata e regolata. `reconcile_decision` /
  `_order_matches` (`omega_engine.py:648-651`) accettano per ref senza selezione e lato;
  `_posizione_da_cleared` (`execution.py:2211-2259`) legge per bet_id la scommessa vera.
  Senza correggerli, una chiusura tradotta via REST verrebbe contabilizzata coi numeri
  dell'ordine vero.
- **Il punto 9 aggrava il quadro**: anche sul canale, il ripiego live di Safe e Omega oltre
  i 20 s rilegge l'ordine vero (§9).
- **Proposta**: prima si correggono le letture dei bot (§9), poi si estende l'equivalente
  alla coda e al REST.
- **Oggi**: sulla coda e sul REST una chiusura Safe sotto 0,50 è un rifiuto certo
  dichiarato; fra 0,50 e 1,00 va al place-and-trim. Sul canale c'è l'equivalente.
- La divergenza fra le strade resta e va decisa dall'utente.

## 5. L'equivalente solo su due esiti esaustivi

- **Prima** (`altro_runner_due_esiti`): bastava `len(runners)==2`. Il buco R8 (`!=2` → `<2`)
  sopravviveva: nessun test con un book a 3 runner.
- **Dopo** (`motore_ordini.py:494`): due runner, entrambi `ACTIVE` (un `REMOVED` cambia il
  mercato) e `market_definition.number_of_winners == 1` quando il book lo porta (0 o 2 →
  niente equivalente).
- **Test**:
  - `test_p5_tre_esiti_mai_equivalente` (motore vero: 3 runner, banca 0,43 → rifiuto, zero
    chiamate);
  - `test_p5_due_runner_ma_non_esaustivi_niente_equivalente` (REMOVED, 2 vincitori,
    0 vincitori);
  - `test_p5_due_esiti_attivi_un_vincitore_equivalente`;
  - `test_p5_equivalente_peggiore_oltre_la_tolleranza_mai_usato`: chiude anche R9, che il
    mattino sopravviveva.
- **Falsificazione**: C10, C11, R8, R9.

## 6. Parcheggio della banca nella banda INVALID_PROFIT_RATIO

- **Fonte nel repo**: `AUDIT_2026-10-01/RICERCA_STAKE_MINIMI_BETFAIR.md`:
  - §2: articolo ufficiale Betfair `360010423978` (21/07/2026), «returns 20% less or 25%
    more than it ought to»;
  - §6, tabella, riga `INVALID_PROFIT_RATIO`: «ratio = arrotondato(size·(p−1)) /
    (size·(p−1)) … per la BACK, e la liability per la LAY, … 0,80 ≤ ratio ≤ 1,25».
  - Il metodo di arrotondamento non è documentato. Pretendo la banda sia con «half up» sia
    con «half even».
  - Le tre misure empiriche dello stesso §2 («0,80 @1,01 sì, 0,79 no»; «0,01 @1,8 sì, @1,79
    no»; «1,49 @1,01 rifiutato comunque») sono tutte spiegate da questa regola. La vecchia
    regola «liability ≥ 0,008» non spiega la terza.
- **Prima**: `1 + 0,008/S` al tick superiore. Per i residui 0,63-0,79 il parcheggio stava a
  1,02, fuori banda (0,70 @1,02 = 0,014 → 0,01, −28,6 %).
- **Dopo** (`trading/submin.py`):
  - `:351` `BANDA_PROFIT_RATIO`, `:357` `rendimento_in_banda`;
  - `:378` `quota_parcheggio_lontano`: il tick PIÙ BASSO, da `1+0,008/S` in su fino a
    `QUOTA_PARCHEGGIO_LAY_MAX=1,20`, con la banca residua in banda. Altrimenti `None`, cioè
    rifiuto;
  - `pianifica_submin` (`:719`): rifiuto dichiarato `SOTTO_MINIMO_NON_PIAZZABILE:
    INVALID_PROFIT_RATIO_PREVISTO …` col residuo se l'ordine FINALE (dopo taglio e riprezzo)
    è fuori banda o se non c'è un parcheggio sicuro. Esempio: punta 0,50 @1,01 → vincita
    0,005 → 0,01, cioè +100 %.
- **Test**:
  - `test_p6_parcheggio_lay_in_banda_per_ogni_residuo[50..99]`: 50 casi, ricalcolo
    INDIPENDENTE della banda nel test, ed è il tick più basso in banda;
  - `test_p6_misure_empiriche_spiegate_dalla_banda` (7 casi);
  - `test_p6_ordine_finale_fuori_banda_rifiuto_dichiarato_nessun_ordine`;
  - `test_p6_parcheggio_070_ora_a_103_non_piu_a_102`.
- **Falsificazione**: C12, C13, C14, C15, R3.
- **Limite (non fatto)**: anche un ordine DIRETTO fra 1,00 e 1,99 può cadere fuori banda
  (1,49 @1,01). Betfair: «doesn't impact all bets below £2». Oggi la banda si verifica solo
  sul place-and-trim. Proposta: estenderla al verdetto per i diretti sotto 2,00.

## 7. Guardie mancanti

- **`omega_market.place_order_live`** (`omega_market.py:731`):
  - prima: nessuna guardia sui minimi;
  - dopo: `min_stake_rules` (gli stessi minimi `minimi_it`, nessuna esenzione) PRIMA della
    rete; sotto il minimo `PlaceRifiutato(error_code=SOTTO_MINIMO_NON_PIAZZABILE)` (rifiuto
    certo, come vuole `execution._esito_rifiuto_certo`);
  - le vie legittime sotto il minimo passano da `place_submin_live`, che chiama questa
    funzione solo con importi ≥ minimo;
  - chiamanti: Safe `execution.py`, Omega `omega_service.py:5514` (manuale REST), Mike
    `service.py:2147`.
- **`order_exec.MIN_STAKE_EUR = 2.0`**:
  - chi lo usa: `order_exec.place_order`, chiamato da `order_worker.py:73` (coda pre-match
    `betfair_order_requests`) e da `stream/odds_http.py:185` (endpoint `/place-order` dell'app,
    ordini manuali reali);
  - dopo: `MIN_STAKE_EUR` = alias di `minimi_it.IT_MIN_BACK`, e la guardia è
    `min_stake_rules` per lato (`order_exec.py:269`).
- **Test**:
  - `test_p7_place_order_live_sotto_minimo_rifiuto_certo_prima_della_rete` (0,43 banca e
    0,99 punta: zero chiamate di rete; 1,00 arriva alla rete finta);
  - `test_p7_order_exec_usa_i_minimi_it`.
- **Falsificazione**: C16, C17.
- **Fuori perimetro, riportato**:
  - il frontend ha un suo «2 €» (`ManualPanel.cert.12set.test.tsx:160`, «BACK sotto il
    minimo Betfair (2 €): bottone SPENTO»);
  - `omega_model.MARKET_QUOTE_MIN_SIZE = 2.0`;
  - `mike/engine.py:67-71` (coperto dalla patch di Mike);
  - i `MIN_STAKE = 2.0` dei bot tennis e sniper;
  - `safe_strategy/bot_service.py:866` `_CANALE_MIN_STAKE` (parametro di strategia).

## 8. Test indeboliti, xfail, commenti

- **D4** (`test_safe_kill_switch_rest_o1::test_kill_attivo_anche_il_sotto_minimo_si_ferma`):
  torna a **0,73** (sotto il minimo 1,00). Commento corretto. Aggiunta la controprova: a
  freno spento la stessa apertura passa DAVVERO dal place-and-trim REST. Falsificazione:
  **C20** (il freno saltato per la via sotto minimo), ROSSA. Con 1,73 sarebbe rimasta verde.
- **D7**: diventa `test_rev_c2_il_minimo_non_blocca_le_chiusure_sotto_il_minimo_vanno_al_trim`:
  - apertura 0,70 senza trim: rifiuto;
  - chiusura 1,40: diretta;
  - chiusura **0,70**: place-and-trim REST, mai diretta;
  - chiusura **0,40**: rifiuto certo `SOTTO_MINIMO_NON_PIAZZABILE`.
  Falsificazione: C21, R6, R13.
- **I 5 test Omega con la manopola `SAFE_MIN_SIZE_LIVE`**: la manopola è tolta da tutti.
  - `test_take_profit_blocca_il_profitto_quasi_pieno`, `test_p_o1_..._greenup` e
    `test_rev_h3_take_profit_integrale_e_greenup_vero`: la LOGICA è provata con **stake 18
    @55** (chiusura 18×55/990 = 1,00, pari al minimo). Cambia solo lo stake DI PROVA, mai la
    regola: soglia 0,9 × 18 × 0,95 = 15,39, minuto ≥ 80. La riga che prima diceva «≥ 4,5»
    ora dice «≥ 15,39».
  - Gemelli coi minimi VERI e lo stake di sempre (5 @55, chiusura 0,28):
    `test_take_profit_a_1000_coi_minimi_veri_rifiuto_dichiarato_posizione_aperta`,
    `test_p_o1_coi_minimi_veri_chiusura_da_028_rifiutata_mai_inviata` e
    `test_rev_h3_take_profit_coi_minimi_veri_rifiutato_e_dichiarato`. Asseriscono: la regola
    SCATTA (`trigger take_profit`, profitto bloccato ≥ 4,5), nessun ordine, closing in
    `error` col codice, `place_rifiutato` critico, posizione ancora `open`.
  - `test_rev_m3_exit_profit_del_parziale_dal_valore_pianificato`: stake 40 di prova; il
    gemello `test_rev_m3_cash_out_parziale_coi_minimi_veri_rifiutato_e_dichiarato` usa 5.
  - `test_rev_m4`: la manopola non serviva, tolta.
  - Falsificazione: C22, R10, R13.
- **Safe** (non chiesto, fatto per coerenza):
  - la manopola non serviva in 3 test su 4 (`test_exit_residuo_dopo_fill_cappato…`,
    `test_residuo_di_uscita_a_tempo…`, `test_rev_m3_green_up_in_coda_resta_greenup`): tolta,
    e restano verdi coi minimi veri (il residuo 0,85 va al trim della coda);
  - resta SOLO in `test_exit_residuo_si_ferma_al_cap_e_logga_una_volta`, dichiarato: collauda
    il tetto dei ritenti con fette da 0,30, che coi minimi veri sono rifiuti certi. Gemello
    nuovo coi minimi veri: `test_exit_residuo_sotto_050_coi_minimi_veri_mai_ordini_un_critical`
    (punto 10).
- **8 xfail**: tutti `strict=True, raises=AssertionError`. Verificato con `--runxfail` che
  falliscono tutti per `AssertionError` (diff dei valori). Eseguiti: 8 xfailed, nessun
  XPASS. Le righe 2,02 / 3,15 / 0,30 di `test_spezza_esatta` restano verdi: descrivono la
  condotta tennis fuori perimetro (reperto 1). Commento aggiunto nel test: non certificano
  quella condotta.
- **Commenti con numeri vecchi corretti** (`2,00/0,50`, «finale ≥ 1,00», «LAY 1.01», «In
  PAPER non si usa mai»):
  - `config_stream.py:223`;
  - `live_order_build.py:60`;
  - `submin.py` (11, 107, 571, 987 e la docstring di `porta_al_minimo_apertura`);
  - `live_order_worker.py` (413, 1302, 1309);
  - `execution.py` (53, 58, 793).

## 9. Doppia chiusura dopo un equivalente

Prove: lettura del codice. Un sotto-agente in sola lettura ha fatto il giro; le due letture
decisive di Omega le ho ricontrollate io (`omega_service.py:3131-3171` filtra per
selezione e lato; `:3174-3221` conferma per bet_id).

- **Runner (CORRETTO)**:
  - `_do_greenup` leggeva le esposizioni della SOLA selezione (`_read_matched_exposures`).
    Dopo una chiusura tradotta la selezione Over sembra ancora aperta (la gamba vera sta su
    Under), quindi un green-up dal ladder dell'app o un flatten del risk engine rifaceva
    l'hedge: seconda chiusura con soldi veri.
  - Dopo (`live_order_worker.py:2307`): in un mercato a due esiti esaustivi la posizione è
    del MERCATO, W = W(questa) + L(altra) e L = L(questa) + W(altra), come già fa il motore
    in `_riduzione_verificata` (29/09).
  - Test: `test_p9_green_up_dopo_chiusura_tradotta_non_rifa_l_hedge` (nessun ordine) e
    `test_p9_green_up_mercato_a_due_esiti_senza_chiusura_chiude_davvero`.
  - Falsificazione: C18.
  - **È un cambio di condotta del green-up dell'app**: con posizioni su ENTRAMBE le
    selezioni di un Over/Under il green-up ora pareggia il mercato. Prima pareggiava solo la
    selezione cliccata, e una posizione già piatta per il mercato veniva «riaperta». Da
    confermare con l'utente.
- **Mike**: in LIVE non passa dal canale. Va in REST diretto (`mike/service.py:142-166`,
  `execution_mode="rest"` :868), e la porta del canale esiste solo `if mode == "paper"`
  (:841-851): **in live nessuna traduzione**. In paper legge solo gli eventi del canale
  (termini chiesti): **nessuna doppia chiusura**. Se un giorno il live di Mike passasse dal
  canale, le letture REST per bet_id (:2443-2446, :2521-2590, :2669-2690, :5673-5715)
  leggerebbero l'ordine vero.
- **Safe** (solo con `SAFE_ORDINI_VIA_CANALE` acceso):
  - percorso normale: legge gli eventi (termini chiesti), nessuna doppia chiusura;
  - **difetto nel bot (NON toccato)**: nel ripiego live oltre `_CANALE_SCADENZA_LIVE_S`
    (20 s, `bot_service.py:864`, `:1047-1057`), `_reconcile_by_bet_id` (:1473-1503) conferma
    sulla riga di chiusura Over lay la size e il prezzo dell'ordine VERO (punta Under
    7,31 @1,06). Lo stato di copertura e il P&L calcolato sono sbagliati, e ne possono
    nascere una seconda chiusura o una chiusura mancata;
  - il regolamento dai cleared per bet_id prende il `profit` vero: la somma è giusta,
    selezione, lato e prezzo in riga no.
- **Omega**: le automatiche sono su Risultato Esatto e HT Score (3+ esiti), quindi mai
  tradotte. Gli ordini manuali o le missioni su Over/Under sì.
  - **Difetto nel bot (NON toccato)** in `_canale_live_oltre_scadenza`
    (`omega_service.py:3174-3221`):
    - con il bet_id: `_flumine_confirm` coi numeri del vero;
    - senza bet_id: `_adotta_per_mercato` (:3131-3171) cerca selezione Over e lato lay, non
      trova la punta Under e marca la chiusura FALLITA (`canale_mai_visto_su_betfair`)
      mentre l'ordine vero è abbinato. **Rischio di doppia chiusura.**
- **Raccomandazione per l'utente**: finché Safe e Omega non sanno leggere una chiusura
  tradotta nel ripiego live, l'equivalente sul canale per quei due bot in LIVE è a rischio.
  Le scelte:
  1. correggere le due letture dei bot (insegnare `tradotto`/`riga_mandata`);
  2. oppure spegnere la traduzione per attore (Safe/Omega live) finché non lo sanno fare.
  Nessuna delle due è nel mio perimetro.

## 10. Reperto 3: cosa fanno Omega e Safe dopo un rifiuto, e cosa fa ora il runner

- **Fatti** (verificati coi test gemelli e dal sotto-agente):
  - **nessun bot ha un ramo per `SOTTO_MINIMO_NON_PIAZZABILE`**: è un errore generico, e
    ogni tentativo crea una riga di chiusura in `error` più `cashout_error`;
  - **Omega**:
    - default `strategy_version=3`, `greenup_mode='off'` (`omega_config.py:221,406-408`): le
      uscite sono PROPOSTE all'utente. 0 richieste automatiche; 1 per ogni firma
      dell'utente (`_manual_cashout`, nessun ritento);
    - `uscite_protezione='automatico'`: almeno 20 s fra i tentativi, tetto 3, poi
      `esaurita` (`omega_proposte.py:68,136,766-865`);
    - green-up V2 automatico: `greenup_retry_s=20`, `greenup_max_attempts=15`, pausa di
      300 s, poi giri ILLIMITATI (`omega_service.py:6677-6790`, `:6212`, `:6340-6347`). Il
      take-profit si ricalcola dall'80'. La posizione resta aperta fino al regolamento;
  - **Safe**:
    - residuo: `residual_retry_s=20`, `residual_max_attempts=15`, poi backoff 5/15/60/300 s
      senza fine (`exits.py:105-106,174-184`);
    - prima uscita: `exit_max_retries=3`, poi `exit_failed` CRITICAL a OGNI tentativo dal 3°
      (`bot_service.py:5633-5658`);
    - la posizione resta `open` e va al regolamento.
- **Runner** (perimetro: Safe `execution`, motore):
  - **nessuna chiamata a Betfair**: fuori canale il rifiuto si decide in casa; sul canale il
    motore risponde con l'ack rifiutato, e si ripete identico a ogni ritento;
  - **un solo CRITICAL per episodio**: `execution.py:492` `_critico_una_volta`. L'episodio è
    la stessa posizione da chiudere (`closes_trade_id`) oppure, per un'apertura, stesso
    mercato/selezione/lato/importo; scade dopo 6 h; la memoria sta sull'oggetto `db` del
    servizio. Applicato a:
    - `place_rifiutato` locale (sotto 0,50, `:870`);
    - `canale_rifiutato` con `SOTTO_MINIMO` (`:638`);
    - `_esito_rifiuto_certo` per `PlaceRifiutato(SOTTO_MINIMO_NON_PIAZZABILE)` del REST
      (`:1080`).
    Le ripetizioni si loggano NON critiche, con `tentativo_nell_episodio`;
  - restano CRITICAL a ogni tentativo i log dei BOT (`exit_failed` di Safe dal 3°
    tentativo, `uscita_automatica_fallita` di Omega): codice dei bot, non toccato.
- **Test**: `test_bot_service.py::test_exit_residuo_sotto_050_coi_minimi_veri_mai_ordini_un_critical`.
  Asserisce: ritenti ≥ 3, tutti `SOTTO_MINIMO`, critical `[True, False, …]`, contatore
  1..n, nessun ordine REST, nessuna riga in coda, posizione `open`.
- **Falsificazione**: C19.

## 11. Come ho isolato il `.env` (export isolato), per riprodurlo

- **Il problema**: nel worktree (sottocartella del checkout principale) `load_dotenv()`
  risale le cartelle e legge il `.env` VERO del principale. Il conftest neutralizza
  interruttori e chiavi Supabase, ma non il resto: per esempio `test_l4…` e `test_l14…` di
  Safe sono rossi nel worktree e verdi fuori.
- **La procedura** (dalla radice del worktree):
  ```
  git archive -o corr.tar HEAD Betfair tactical_engine value_engine market_intelligence Prediction tools football_data_scraper ":(glob)*.py"
  mkdir <cartella fuori dal repo>/corr && tar -xf corr.tar -C <...>/corr
  cd <...>/corr && "C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/.venv/Scripts/python.exe" -m pytest -q -p no:cacheprovider <file>
  ```
  - io ho usato lo scratchpad della sessione: niente `.env` lungo il percorso, niente
    junction, interprete del principale con percorso assoluto;
  - la base si ottiene con lo stesso comando su `master`, al posto di `HEAD`;
  - nell'export mancano `migrations/` e `frontend/`: 8 test che li leggono (migrazioni SQL,
    chiavi dei finti del frontend) sono rossi sia su base sia su patch, e nel worktree
    passano (147 passed nei 5 file).
- **Numeri finali** (export di `7e34f3c`):

  | set | patch | base `master` |
  |---|---|---|
  | 33 file di test toccati più quelli nuovi | 1244 passed, 3 failed, 2 skipped, 8 xfailed (56,8 s) | 1125 passed, 3 failed: gli stessi 3, preesistenti e dipendenti dall'ordine (`test_l14_ttl…`, `test_cert::test_i_due_motori…`, `test_cert::test_parita_default…`) |
  | 117 file collegati non toccati | 2444 passed, 8 failed, 20 skipped (184 s) | 2444 passed, 8 failed, identici |
  | `tennis_live/tests` + motore + test nuovi (worktree) | 815 passed, 8 xfailed | — |
  | Omega greenup + audit in quest'ordine | `test_l03_stats_azzerate_a_bot_fermo` rosso | rosso anche sulla base e sulla patch del 01/10: preesistente, dipendente dall'ordine |

- **Test di tempo**: `test_latenza_logica_aggancio_sotto_i_20_ms` e
  `test_latenza_logica_comando_place_sotto_20_ms` misurano il tempo. Sono caduti una volta
  ciascuno con la macchina sotto carico; ripetuti da soli sono verdi su base e su patch.

## 12. Patch di Mike

`git apply --3way --check` di `MIKE_CHIUSURA_COPERTURA.patch` (copia LF) sopra
`verifica-runner`:
- 13 file puliti;
- 2 nuovi;
- unico conflitto `Betfair/stream/trading/minimi_it.py` (add/add, come il mattino).

Va tenuta la versione del runner: è un superinsieme, e Mike importa `IT_MIN_BACK`,
`IT_MIN_LAY`, `SUBMIN_IMPORTO_FINALE_MIN` e `IT_FLOOR_LEGGE`.

Mike vedrà ora `error_code` anche negli eventi asincroni: il delegato di Mike oggi legge il
codice dal testo del `motivo`.

## 12-bis. Punto 11: traduzione solo per gli attori che sanno riconciliarla

Decisione del coordinatore: un ordine tradotto nell'equivalente è ammesso SOLO per chi sa
riconciliarlo. Commit `2081711`.

- **Codice**:
  - `trading/minimi_it.py`: `ATTORI_CON_TRADUZIONE: frozenset = frozenset()`. È **vuoto**,
    e il commento dice «chi sa riconciliare un ordine tradotto nello specchio, nei cleared
    e nei ripieghi REST» e perché oggi non c'è nessuno:
    - Safe e Omega: i due difetti del §9, che un altro delegato sta correggendo;
    - Mike: in live non passa dal canale e ha la sua patch;
    - ordini manuali dell'app (`desktop`): aspettano la conferma del green-up di mercato.
  - `motore_ordini._applica_minimi`: l'unico punto dove si decide «equivalente»; worker,
    coda e REST non traducono mai. Se l'attore del comando (`strategy_ref`, che
    `valida_comando` impone uguale all'`attore`) non è nell'insieme, l'altra selezione non
    si passa al verdetto. Il verdetto allora va: diretto → place-and-trim (finale ≥ 0,50)
    → rifiuto `SOTTO_MINIMO_NON_PIAZZABILE`. Il motivo dice «equivalente NON ammesso per
    l'attore '…' (ATTORI_CON_TRADUZIONE)» e porta il residuo da dichiarare.
  - `live_order_build.verdetto_minimi`: nuovo parametro opzionale `motivo_no_equivalente`,
    solo per il testo del motivo.
  - Paper e live uguali (il motore non guarda il modo).
  - Un solo CRITICAL per episodio sul lato Safe (`_critico_una_volta`), già fatto al punto 10.
- **Correzione nata dai test**: il motivo del `Rifiuto` era tagliato a 240 caratteri, e il
  residuo «da dichiarare al trader» (in coda al motivo) spariva dall'ack. Ora 480.
- **Test** (`test_runner_minimi_correzioni_2026_10_02.py`):
  - `test_p11_insieme_degli_attori_con_traduzione_oggi_vuoto`;
  - `test_p11_banca_043_mai_tradotta_rifiuto_col_codice[paper|live × safe, safe_tennis, omega, mike, desktop]`:
    10 casi; zero ordini, ack col codice, motivo dell'attore e residuo;
  - `test_p11_banca_070_mai_tradotta_va_al_place_and_trim_sulla_stessa_selezione[safe, safe_tennis, omega]`:
    il parcheggio sta sull'Over, banca 1,00 @1,03, mai l'Under;
  - `test_p11_attore_nell_insieme_traduzione_resta`: con 'omega' nell'insieme la
    traduzione c'è (punta Under 7,31 @1,06); 'safe', nello stesso processo, no;
  - `test_p11_safe_sul_canale_un_solo_critical_per_episodio`: tre ritenti col rifiuto del
    runner danno critical `[True, False, False]`.
- **Test della MACCHINA della traduzione** (punti 1 e 3, e due test del delegato del 01/10:
  `test_motore_banca_043…`, `test_motore_aggancio_ripete…`): abilitano 'mike' e 'safe' SOLO
  per la prova, con una fixture dichiarata (`traduzione`, `traduzione_mike`) che fa
  `monkeypatch` di `ATTORI_CON_TRADUZIONE`. Senza, sarebbero 8 rossi (verificato) e la
  macchina non sarebbe più collaudata.
- **Falsificazione**: C24 (insieme ignorato: traduzione per tutti), C25 (Safe e Omega
  aggiunti a mano), C26 (insieme svuotato anche per chi c'è), C27 (motivo tagliato, residuo
  perso). Esito qui sotto.
- **Test mirati** (export di `2081711`):
  - file toccati: **1260 passed, 3 failed, 2 skipped, 8 xfailed**. I 3 rossi sono gli
    stessi preesistenti della base;
  - 117 file collegati: **2444 passed, 8 failed**, gli 8 d'ambiente di sempre.

FALSIFICA_P11

### Il green-up del ladder dell'app, per l'utente (cosa cambia a schermo)

- **Caso**: hai due posizioni sullo stesso Over/Under 2,5, punta Over 10 € @2,00 e punta
  Under 10 € @2,00. Il mercato è già in pari: vinca chi vinca, fai 0 €.
- **Prima**, cliccando «green-up» sull'Over, il runner guardava solo l'Over (+10 / −10) e
  mandava una banca Over di circa 9,76 € @2,05. Ti ritrovavi esposto: −10,25 € se vince
  l'Over, +9,76 € se vince l'Under.
- **Ora** guarda il mercato intero: vede 0 € / 0 €, non manda nessun ordine e scrive
  «posizione già piatta».
- **Con posizioni diverse**: per esempio punta Over 10 € @3,00 e punta Under 5 € @1,50. Prima
  si chiudeva solo l'Over: banca circa 9,84 € e l'Under restava scoperto. Ora una sola banca
  Over di circa 7,38 € pareggia l'intero mercato, circa −0,1 € su entrambi gli esiti.
- **Con una posizione sola** (il caso tipico) a schermo non cambia nulla.

## 13. NON VERIFICATO

- **Nessun ordine vero**. Restano da provare dal vivo, con ordini piccoli decisi dall'utente:
  - la banda `INVALID_PROFIT_RATIO` (quale grandezza confronta Betfair, e come arrotonda);
  - il parcheggio LAY a 1,03 per 0,70;
  - l'equivalente 7,31 @1,06;
  - il cancel parziale di un ordine tradotto.
- **Place-and-trim SINCRONO in paper sul client simulato vero, da capo a fondo** (thread
  pool di flumine, latenze reali): verificato sul codice di flumine e coi finti; non con
  una `SimulatedExecution` vera in un runner paper acceso.
- Il replace tradotto con un abbinamento parziale DURANTE il cancel: la formula è nel
  codice (resto al cancel − abbinato nel frattempo), ma senza un test dedicato.
- I due difetti dei bot (§9): letti nel codice, non riprodotti con un test.
- Mike, `_rileggi_ordine_appoggiato` in paper: non letto.
- Se la memoria della porta riceve di nuovo gli eventi dopo un riavvio del bot (quanto è
  probabile il ripiego oltre 20 s).
- Suite intera e replay: non lanciati, come da brief.
