# SCALPER TENNIS: difetto CP4 sulla chiusura abbinata in parte (07/10/2026)

Delegato del coordinatore. Lavoro NON committato nel worktree
`/home/user/python-database-automation/.claude/worktrees/agent-a200463f056889151`
(base `8226d766`).

## 1. Causa radice

**Reperto.** Comando del coordinatore:
`python3 -m Betfair.stream.backtest.certifica tennis_scalper 35790089 --data-dir /home/user/python-database-automation/_live_raw_tennis/20260707 --scenari chiusura-abbinata-in-parte --worker 1`.
Esito KO, CP4 x1: chiusura LAY che «chiede di spostare il netto di 2.02 quando da chiudere ne resta 1.46».
L'ho riprodotto identico (`replay_scalper_tennis_cp4/chiusura_parziale_prima.txt`).

**Traccia degli ordini sulla selezione 9633138.** Script spia sul guasto del banco, solo lettura, nello scratchpad.

| ora | ordine | abbinato | netto da chiudere |
|---|---|---|---|
| 12:29:02 | ingresso BACK 2,00 @1,21 | 2,00 | |
| 12:34:18 | close a target LAY 1,68 @1,44 (colpita dal guasto) | 0,67 (1,01 annullati) | 2,42 prima della close |
| 12:35:47 | **LAY 2,00 @1,01**, il parcheggio del place-and-trim | 0 | 1,46 |

Dopo la close, il flatten calcola correttamente sull'abbinato: LAY 0,98 @1,49 (0,98 × 1,49 = 1,46).
Lo 0,98 è sotto il minimo .it della banca (1,00), quindi passa dal place-and-trim:

1. parcheggio a quota non abbinabile;
2. taglio a 0,98;
3. rimpiazzo alla quota vera.

L'ordine accusato da CP4 è il parcheggio. Se si abbinasse prima del taglio (il rischio per cui `trading/submin` ha la guardia-abort), sposterebbe il netto di 2,00 × 1,01 = 2,02. Da chiudere c'è 1,46: la posizione si rovescerebbe di 0,56.

**Dove sta nel codice.** `Betfair/stream/tennis_scalper/tennis_scalper_bot.py`, `TennisScalperStrategy._place_exact`, riga 2722 prima della correzione:
`placed_size=2.0,          # park legale/universale (.it)`.
- Lo `SubminState` era costruito a mano con 2,00, il vecchio minimo della PUNTA, in vigore prima dei minimi .it del 01/10.
- La fonte unica dice 1,00 per i due lati: `trading/submin.place_min_size` legge `trading/minimi_it` (`IT_MIN_BACK` / `IT_MIN_LAY` = 1,00).
- Pro/FLB/swing fanno già così: `condotta_ordini.UsciteEsatte.piazza`, riga 402, `placed_size=IT_BACK_MIN_STAKE`. Lo scalper tennis era l'unico rimasto col numero copiato.

**Confronto col calcio.** La correzione CP4 dello scalper calcio del 04/10 (`CERTIFICAZIONE_SCALPER_CALCIO.md`) era un'altra:
- lo scratch che piazzava la chiusura nuova con quella vecchia ancora viva (tipo «viva»);
- più la spartizione `spezza_uscita` / `minimi_it.importo_piazzabile` e il residuo ricordato.

Lo scalper tennis aveva già quella spartizione. L'ho verificata caso per caso contro `spezza_uscita` su LAY 0,98 / 0,30 e BACK 0,70 / 1,37 / 1,70 / 1,95: stesse parti diretta, place-and-trim e residuo. Aveva già anche il residuo ricordato (`slot.resto_np` → `residui_ricordati.dichiara`). Qui il tipo di CP4 è «sovrarichiesta» e la causa è il parcheggio.

**Lo scalper calcio ha lo stesso numero copiato.** `Betfair/stream/scalper/scalper_bot.py:2867` e `sniper_bot.py:1162` hanno `placed_size=2.0`: è un difetto latente, vedi §6. Non l'ho toccato: è fuori perimetro.

## 2. Cosa ho cambiato

**File toccato: `Betfair/stream/tennis_scalper/tennis_scalper_bot.py`** (`_place_exact`, +13/−4).
- `placed_size=round(float(place_min_size(JURISDICTION_IT, side.lower())), 2)`, dalla fonte unica `trading/submin`, al posto di `2.0`.
- Docstring aggiornata e ASCII.
- Invariati:
  - quota del parcheggio (BACK 1000, LAY 1,01);
  - importo finale, cioè la spartizione;
  - prezzo della chiusura e rimpiazzo;
  - anti-cascata, tetti, soglie e strategia.
- La riduzione del taglio diventa `1,00 − target` invece di `2,00 − target`. Il target è sempre < 1,00: una punta ≥ 1,00 non multipla va diretta più residuo sotto 0,50, mai in sequenza.

**File nuovo: `Betfair/stream/tennis_live/tests/test_scalper_tennis_cp4_parcheggio_2026_10_07.py`.**
- `test_parcheggio_non_chiede_piu_di_quanto_resta_da_chiudere[1,4]`. Scalper VERO nel runner paper vero (Flumine, `SimulatedExecution`, latenza 1 e 4 book). Posizione: ingresso BACK 2,00 @2,10 più close LAY 2,00 @2,10 abbinata in parte (1,40 abbinati, 0,60 in `size_cancelled`), creata come ordine flumine con `size_matched`, `size_remaining`, `size_cancelled`, `size_lapsed` veri. Ogni ordine nuovo si giudica all'esecuzione con le funzioni del banco (`chiusura_parziale.direzione`, `tolleranza`, `vivo`, `residuo`, `lato`), cioè la formula di CP4. Asserisce anche:
  - parcheggio = minimo .it;
  - chiusura esatta: |se vince − se perde| ≤ 0,01;
  - nessun ordine vivo.
- `test_parcheggio_della_sequenza_e_il_minimo_di_giurisdizione[LAY-1.01, BACK-1000.0]`: lo stato della sequenza nasce col minimo della fonte unica per i due lati; quota e riduzione coerenti.

**File di referto:** questo, più `AUDIT_2026-10-07/replay_scalper_tennis_cp4/`, 4 file, 88 KB:
- `tennis_scalper_tutti_dopo.txt`;
- `chiusura_parziale_prima.txt`;
- `chiusura_parziale_dopo.txt`;
- `chiusura_parziale_mutazione_M1.txt`.

Nessun altro file toccato. Non ho toccato `tennis_runner.py`, `tennis_recorder.py`, `scalper/**`, `backtest/**`, `tennis_replay/**` e il frontend.

## 3. Test, replay, falsificazione

**TDD.**

| fase | esito |
|---|---|
| ROSSO sul codice del ramo | 4 rossi su 4; il principale dice `LAY 2.00 @1.01 chiede di spostare il netto di 2.02 quando da chiudere ne resta 1.26`, la stessa firma del banco |
| VERDE dopo la correzione | 4 passati, 4,1 s |

Comando: `python3 -m pytest Betfair/stream/tennis_live/tests/test_scalper_tennis_cp4_parcheggio_2026_10_07.py -q -p no:cacheprovider`.

**Test esistenti, sul codice corretto.**

| comando | esito |
|---|---|
| `python3 -m pytest Betfair/stream/tennis_live/tests Betfair/stream/tennis_scalper/tests -q -p no:cacheprovider` | **1031 passati, 4 skipped, 5 xfailed, 0 rossi** (45,5 s) |
| `Betfair/stream/tests/`: `test_submin.py`, `test_submin_contratto_chiamanti_2026_09_17.py`, `test_submin_nucleo_2026_09_17.py`, `test_firma_scaduta_ttl_n3_2026_09_28.py`, `test_proposta_sempre_coi_numeri_2026_09_29.py`, `test_stato_mercato_freno_2026_09_24.py`, `test_contratto_strada_unica_2026_09_25.py` | **142 passati** (19,5 s) |
| `Betfair/stream/tests/`: `test_registro_impronta_2026_09_30.py`, `test_registro_bot_2026_09_16.py`, `test_banco_uscite_dichiarate_n3_2026_09_28.py`, `test_banco_uscite_manuali_n3_2026_09_28.py`, `test_valuta_k1_2026_09_26.py`, `test_cert_banco_2026_09_16.py` | **189 passati, 11 skipped** (12 s) |

**Replay, `--scenari tutti`, sulla 35790089.** Comando:
`python3 -m Betfair.stream.backtest.certifica tennis_scalper 35790089 --data-dir /home/user/python-database-automation/_live_raw_tennis/20260707 --scenari tutti --worker 1`.
- Esito: **17 su 17 OK, 0 violazioni**, 102,2 s (prima 99,8 s; tetto 600).
- Confronto con il referto del coordinatore, tolte le sole righe dei tempi (`diff`): cambiano soltanto
  1. intestazione: percorso della `--data-dir` (assoluto) e hash del codice del bot (`dc69630bf428` → `4a798ba1975b`), effetto del diff;
  2. `chiusura-abbinata-in-parte`: KO → OK, sparite le due righe CP4;
  3. ESITO: 16 → 17 senza violazioni, 1 → 0 violazioni totali.
- Tutto il resto è identico riga per riga: tick, decisioni, azioni, stati, note, RESIDUI, copertura dei controlli (CP1 x9754, CP3 x9754, CP4 x5010 come prima). Il parcheggio non si abbina mai su questa registrazione (1,01 / 1000): cambia solo l'importo chiesto del gradino 1, quindi abbinamenti, P&L e residui restano gli stessi.

| scenario | prima (coordinatore) | dopo | tick | decisioni | azioni | stati |
|---|---|---|---|---|---|---|
| base | OK | OK | 5216 | 5212 | 1 | IDLE |
| gate-aperto | OK | OK | 5216 | 5212 | 99 | QUOTING2,CANCELLING,IDLE,FLATTENING,DONE,LOCKING |
| dry-run | OK | OK | 5216 | 5212 | 1 | IDLE |
| bot-fermo | OK | OK | 5216 | 2483 | 1 | IDLE |
| rifiuti-betfair | OK | OK | 5216 | 5212 | 80 | IDLE |
| feed-stantio | OK | OK | 5216 | 5212 | 1 | IDLE |
| parziali | OK | OK | 5216 | 5212 | 1 | IDLE |
| riavvio | OK | OK | 5216 | 5212 | 2 | IDLE |
| catalogo-assente | OK | OK | 5216 | 5212 | 1 | IDLE |
| live | OK | OK | 5216 | 5212 | 99 | come gate-aperto |
| **chiusura-abbinata-in-parte** | **KO CP4 x1** | **OK** | 5216 | 5212 | 85 | QUOTING2,CANCELLING,IDLE,FLATTENING,DONE |
| chiudi-ora | OK | OK | 5216 | 2574 | 100 | come gate-aperto |
| uscite-manuali | OK | OK | 5216 | 5212 | 214 | come gate-aperto |
| uscite-manuali-firmate | OK | OK | 5216 | 5212 | 70 | come gate-aperto |
| soldi-veri | OK | OK | 5216 | 5212 | 99 | come gate-aperto |
| soldi-veri-prova | OK | OK | 5216 | 5212 | 80 | IDLE |
| soldi-veri-paper | OK | OK | 5216 | 5212 | 99 | come gate-aperto |

Tick, decisioni, azioni e stati sono identici prima e dopo in tutte le 17 righe.

**Falsificazione.** Patch salvata, ripristino con `git checkout -- <file>` più `git apply --include`. Dopo il ripristino: `grep -c MUTAZIONE` = 0, `git diff --stat` e `git diff` identici a prima.

| # | mutazione | test nuovo | scenario del banco |
|---|---|---|---|
| M1 | `placed_size=2.0` (il difetto) | **4 rossi su 4** | **KO CP4 x1**, stesso messaggio 2.02 / 1.46 (`chiusura_parziale_mutazione_M1.txt`) |
| M2 | `placed_size=1.5` (parcheggio sopra il minimo) | **4 rossi su 4** (`LAY 1.50 @1.01 ... 1.52 ... 1.26`) | non lanciato: 1,5 × 1,01 = 1,515 sta nella tolleranza di CP4 su questa registrazione (1,46 × 1,02 + 0,065 = 1,554), quindi il banco non lo vedrebbe; lo vede il test |

## 4. Migrazioni SQL
Nessuna.

## 5. Parità paper/live
`_place_exact` è la stessa funzione in paper e in live. Ci si arriva con `exact_exits` e senza `dry_run`, e il runner tennis la accende in entrambe le modalità.
- La modifica non legge la modalità: il parcheggio è 1,00 in paper e in live, sulla stessa quota e con la stessa sequenza.
- Prova:
  - il test gira sul runner PAPER vero;
  - gli scenari `live`, `soldi-veri`, `soldi-veri-prova` e `soldi-veri-paper` sono identici al riferimento, numero per numero;
  - in dry-run niente sequenze, come prima (scenario `dry-run` identico).

## 6. Cosa NON ho fatto e cosa NON ho potuto verificare

1. **Scalper calcio e sniper: stesso numero copiato, non corretto (fuori perimetro).**
   - Dove: `Betfair/stream/scalper/scalper_bot.py:2867` e `Betfair/stream/scalper/sniper_bot.py:1162`, `placed_size=2.0`.
   - Rischio: identico. Dopo una chiusura abbinata in parte, una banca sotto 1,00 parcheggiata 2,00 @1,01 può rovesciare la posizione se il parcheggio si abbina.
   - Perché il banco non l'ha visto: sulle registrazioni del calcio il caso non si è presentato.
   - Proposta: la stessa riga, `place_min_size(JURISDICTION_IT, side)`, con un test gemello.
2. **Quota del parcheggio LAY fuori dalla banda INVALID_PROFIT_RATIO: difetto latente, NON corretto, è una proposta.**
   - Lo scalper tennis costruisce lo `SubminState` a mano e salta il pianificatore condiviso `trading/submin.pianifica_submin` / `start_submin`.
   - Per una banca residua fra 0,50 e 0,79 il parcheggio resta a 1,01. Esempio: 0,70 @1,01 ha liability 0,007, arrotondata a 0,01, cioè +43 %, e `rendimento_in_banda(0.70, 1.01)` = False.
   - La quota giusta è `quota_parcheggio_lontano('lay', 0.70)` = 1,03 (0,50-0,60 → 1,02).
   - Su Betfair vero il taglio sarebbe rifiutato (documentato in `submin.py`, righe 64-71 e 380-400).
   - Il banco non simula INVALID_PROFIT_RATIO: `minimi_banco` non lo conosce, quindi il replay non può vederlo.
   - Perché non l'ho corretto: spostare il parcheggio da 1,01 cambia il riconoscimento del parcheggio in due posti, che non si possono toccare senza riaprire la certificazione:
     - `_drive_flatten`: `p <= 1.011` lo esenta dallo «stantio»; a 1,03 il flatten lo annullerebbe;
     - il controllo del banco: `tennis_live/certificazione_bot._QUOTA_PARCHEGGIO = {"LAY": 1.01}`.
   - Lo stesso vale per pro/FLB/swing (`condotta_ordini`) e per il calcio.
   - Proposta: un cantiere dedicato. Lo `SubminState` si costruisce con `park_price=quota_parcheggio_lontano(...)` (None = residuo dichiarato); il parcheggio si riconosce per appartenenza alla sequenza e non per quota; il controllo del banco usa la stessa funzione.
3. **Il pianificatore condiviso (percorso A, parcheggio alla quota target senza replace) non è adottato.** Il bot usa sempre il percorso B.
   - Il «reperto 25» (17/09, `submin.py` righe 541-552) dice che in-play il rimpiazzo del gradino 3 fallisce (`CANCELLED_NOT_PLACED`).
   - Lo scalper tennis opera anche in-play: in soldi veri le sue chiusure sotto 1,00 in-play rischiano di non completarsi.
   - Il banco non simula quel rifiuto, quindi non verificabile qui. Va nel cantiere del punto 2.
4. **CP4 e il parcheggio BACK @1000** (osservazione sul banco, fuori perimetro).
   - La formula di CP4 conta capacità = size × quota: un parcheggio BACK 1,00 @1000 vale 1000 di netto, e quindi sarebbe sempre «sovrarichiesta» dopo una chiusura colpita.
   - Su questa registrazione non succede: dopo la BACK colpita (35635727) non è partito nessun place-and-trim BACK.
   - Se capitasse, il KO sarebbe del banco e non del bot. Va deciso con chi tiene il banco (`backtest/chiusura_parziale.py`).
5. Non ho rilanciato la suite intera `pytest Betfair/` (vietato dal brief) né altri bot. Ho rilanciato solo i pacchetti tennis e i test collegati elencati al §3.
6. **Non verificato dal vivo:** che Betfair .it accetti il parcheggio BANCA 1,00 @1,01 con taglio a 0,98. Secondo `minimi_it` e `submin` è legale (diretto ≥ 1,00, finale ≥ 0,50, liability residua 0,0098 → 0,01, in banda). Pro/FLB/swing usano già 1,00.

## 7. Decisioni per l'utente
Nessuna decisione di trading toccata: quando chiudere, quota, importo finale, soglie e stake sono invariati. Cambia solo la taglia del parcheggio tecnico del place-and-trim.

Da portare all'utente, solo come informazione e senza proposta di cambiare la strategia: anche col parcheggio al minimo resta un rischio teorico, inerente al place-and-trim deciso dall'utente il 04/10 («sotto 1 euro place and trim»).
- Una banca di chiusura piccola a quota bassa, per esempio 0,60 @1,30 (netto 0,78), si parcheggia 1,00 @1,01: se il parcheggio si abbinasse prima del taglio, la copertura sarebbe di 1,01 contro 0,78.
- La guardia-abort di `submin` ferma la sequenza ma non annulla l'abbinato.
- Oggi non esiste un parcheggio più piccolo di 1,00 su .it.

## 8. Da controllare dal vivo in paper al prossimo avvio
- Una chiusura dello scalper tennis sotto 1,00 (attività `submin_start` del bot `tennis_scalper`) deve avere il parcheggio a **1,00**, non 2,00:
  - quota 1,01 per la banca, 1000 per la punta;
  - poi il taglio (`size_cancelled` = 1,00 − importo) e il rimpiazzo alla quota della chiusura.
  - Dove: specchio `tennis_live_orders` (riga del parcheggio: chiesto 1,00) e il blotter del Terminale.
- A chiusura completata, il netto della selezione deve essere pari al centesimo, oppure il residuo dichiarato (riga CRITICAL `residuo_non_piazzabile`).
