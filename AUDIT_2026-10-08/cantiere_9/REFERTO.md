# CANTIERE 9 - Scalper/sniper CALCIO: scavalco, tetto di perdita, rifiuti Betfair (copertura del banco)

Delegato di costruzione cloud, 08/10/2026. Worktree `agent-acf5e90f86ae32c4b`, portato con fast-forward
alla cima integrata `3b8ce19` (cantiere 15 compreso). Nessun commit, nessun `git add`.
Container: 4 CPU condivise, carico medio 4-21 durante le misure: i tempi di parete sono indicativi.

## IN TESTA (regola del cantiere): una riga del BOT e' cambiata

`Betfair/stream/scalper/scalper_bot.py` (`_drive_submins`, righe 3224-3234): quando il parcheggio del
place-and-trim muore perche' Betfair lo ha RIFIUTATO, la riga `submin_abort` dice il codice
(`order.responses.place_response.error_code`, letto con la funzione che il bot ha gia', `_codice_rifiuto`)
e porta il campo `codice`. Senza codice la riga e' identica a prima. Solo telemetria: nessuna decisione
di trading, nessun ordine, nessuna soglia cambiata.
- Bug dimostrato dal banco: scenario nuovo `rifiuti-betfair-codici`, controllo RC3 rosso
  («rifiuto INVALID_PROFIT_RATIO (parcheggio) mai scritto col codice nell'attivita' del bot»).
- Test rosso -> verde: `test_scalper_scrive_il_codice_del_parcheggio_rifiutato` (2 casi). Mutazione
  BM-RC3 (`codice = None`): 1 rosso; ripristino sha256 `1f570ce9714bde2f` identico.
- Il file e' nel perimetro di W3b (consapevolezza ordini esterni): l'hunk e' piccolo e isolato, va
  integrato con attenzione. Stesso difetto, NON toccato: `sniper_bot.py:1322` e
  `tennis_scalper_bot.py:2850` (stessa riga senza codice; vedi Decisioni).

## 0. Esito in una riga

Banco: scenario nuovo dell'ingresso abbinato in parte sotto 0,50 (scavalco) e scenario nuovo del finto
Betfair coi codici veri, live e prova, con controlli SV1-SV5 e RC1-RC4 dal mercato; reperto 7.2 del
cantiere 5 corretto (`uscite_manuali.e_parcheggio` riconosce il parcheggio LAY 1,01-1,03 dalla fonte
unica). I 7 scenari di riferimento su 35797769 e 35760084 sono **identici** prima/dopo. Lo scenario
`rifiuti-betfair-codici` resta **KO per un solo controllo, RC3 sul rimpiazzo rifiutato**: il codice
`BET_TAKEN_OR_LAPSED` di `replaceOrders` non arriva a nessuno (flumine lo scarta, anche in produzione), e
il bot scrive «submin completato: ordine a riposo» per un ordine che non esiste. Decisione D1 sotto.

## 1. Cosa ho cambiato (file:riga) e perche'

| file | righe | cosa |
|---|---|---|
| `Betfair/stream/backtest/uscite_manuali.py` | 63-86, 504-506 | `e_parcheggio`: BACK solo 1000 (invariato); LAY una delle quote di `tennis_scalper.condotta_ordini.QUOTE_PARCHEGGIO_LAY` (calcolate da `trading.submin.quota_parcheggio_lontano` sui resti 0,50-0,99: oggi 1,01/1,02/1,03; la stessa tupla del banco tennis B8/B11, nessuna copia). Commento di UF2 aggiornato. |
| `Betfair/stream/backtest/scavalco_rifiuti.py` | nuovo (~1000 righe) | i due guasti e i controlli (sez. 2). |
| `Betfair/stream/scalper/tools/replay_registrazioni.py` | 106, 843-845, 938-939, 1846-1848, 2733-2735, 2932-2933, 3362-3371, 3825-3830 | aggancio ADDITIVO: import, 4 scenari in `SCENARI_DESCRITTI`, `dry_run` delle varianti `-paper`, lista `sorveglianze_extra` (vuota negli altri scenari: nessuna riga, nessun costo), chiamata per book e per giro, montaggio nello scenario, riepilogo nel referto. **Fuori dal mio perimetro stretto e dentro quello di W3b**: dichiarato, hunk additivi. |
| `Betfair/stream/backtest/applica_bot.py` | 195-197 | i 4 scenari classificati `_GUASTO` in `SCENARI_SCARTATI["scalper_calcio"]` (il test di contratto lo pretende). |
| `Betfair/stream/scalper/scalper_bot.py` | 3224-3234 | vedi «IN TESTA». |
| test nuovi | - | `test_banco_uf2_parcheggio_lay_2026_10_08.py` (56), `test_banco_scavalco_rifiuti_2026_10_08.py` (37). |

## 2. Gli scenari nuovi (banco comune `backtest/scavalco_rifiuti.py`)

**Guasto 1, «ingresso abbinato in parte»** (`ingresso-abbinato-in-parte`, `-paper`).
- Il primo gruppo di ingressi di ogni selezione (le gambe del maker vive insieme; ruolo dalla credenza
  vera del bot, `banco.ruolo_ordine`) trova il mercato sottile: tutte insieme abbinano al piu' 0,29 (la
  BACK 0,29 del reperto R4 del 07/10).
- Non e' un fill a mano: il guasto avvolge `SimulatedOrder._update_matched` come
  `chiusura_parziale._tetta_abbinato`; prezzi, istanti, coda e mercato che attraversa restano di flumine.
- Finito il gruppo (gambe morte), il mercato torna quello registrato. Un gruppo morto senza abbinato si
  riarma sul gruppo dopo (2 riarmi su 35797769).

**Guasto 2, «finto Betfair coi codici veri»** (`rifiuti-betfair-codici`, `-paper`, sopra il guasto 1).
- Il PRIMO scavalco riceve `INVALID_BET_SIZE` (placeOrders), il PRIMO parcheggio del place-and-trim
  `INVALID_PROFIT_RATIO` (placeOrders), il PRIMO rimpiazzo `BET_TAKEN_OR_LAPSED` (replaceOrders, parte place).
- Risposta = l'oggetto che la simulazione di flumine usa per i SUOI rifiuti
  (`SimulatedPlaceResponse(status="FAILURE", error_code=...)`). Stesse chiavi della
  `PlaceInstructionReport` vera di betfairlightweight (test che lo verifica, tolta l'eco `instruction`).
- Size tolta come fa flumine (`size_voided`, `size_lapsed`); `order.responses.place_response.error_code`
  e' quello che il bot legge.
- Rimpiazzo rifiutato come in produzione: `BetfairExecution.execute_replace` crea il sostituto solo su
  SUCCESS, quindi qui il sostituto esce dal `Trade` e non entra nel blotter. Il parcheggio resta annullato
  (Betfair replaceOrders: la cancel non si ritira).
- Il rifiuto della `replace` tocca la parte place, non il taglio (cancelOrders): la specifica chiede
  placeOrders/replaceOrders.

**I controlli** (famiglie nuove, registro separato: la copertura stampata dei 22 controlli non cambia).
Si giudicano dal blotter e dagli abbinati veri; la credenza solo dove il controllo e' credenza contro
mercato.
- **SV1**: dopo un ingresso sotto il floor lo scavalco parte entro 5 book del mercato. Abbinato lo
  scavalco e passata la pausa anti-churn che il bot dichiara (`flatten_min_interval_ms`), la chiusura
  parte entro 5 book. Un book = un istante di pubblicazione NUOVO di quel mercato (sez. 4, reperto R-SV1).
- **SV2**: a ciclo chiuso posizione piatta, |se vince - se perde| <= 0,02. Un resto e' ammesso solo dopo
  3 scavalchi E dichiarato (`residuo_ricordato`).
- **SV3**: al piu' 3 scavalchi per ciclo. Test di contratto: uguale a `_SCAVALCHI_MAX_PER_CICLO` di
  maker e sniper.
- **SV4**: ogni scavalco a mercato ha la sua attivita' `scavalco` (lato, quota, importo).
- **SV5**: ogni `loss_cap` porta le due cifre (perdite vere, residui esclusi) e scatta solo con le
  perdite vere oltre il tetto.
- **RC1**: nessuna posizione fantasma. Una sequenza che aspetta un ordine rifiutato, o uno slot vivo che
  poggia solo su lui, oltre 3 giri e' violazione. Nota: K2 non vede i rifiuti coi codici, perche' lo stato
  e' EXECUTION_COMPLETE e non Violation.
- **RC2**: niente loop, al piu' 10 ordini nuovi dopo il rifiuto (`CP.TETTO_RIPIAZZAMENTI`).
- **RC3**: il rifiuto e' scritto col suo codice entro 3 giri.
- **RC4**: a ciclo chiuso la posizione e' piatta o il residuo e' dichiarato.
- Il primo ingresso NUOVO dopo il ciclo lo chiude (il bot e' ripartito); i suoi ordini non sono del
  ciclo (reperto R-BF1, sez. 4).
- Nota `impronta degli ordini del bot`: sha degli ordini senza id ne' bet_id, per la parita' paper/live.

## 3. Tabella «caso -> ordini mandati -> risposta -> stato finale» (35797769, replay finale)

Fonti: `finale_35797769.txt`, `traccia_ingresso_sel22_58805.txt`, `traccia_codici_sel58805.txt`.

| caso | ordini del bot | risposta | stato finale della posizione |
|---|---|---|---|
| sel 58805, ingresso LAY 25 @4,2 abbinato 0,29 (16:51:55), chiusura BACK 0,29 sotto il floor | `min_bet_skip` BACK 0,28/0,30; **scavalco** LAY 1,67 @4,2; chiusura BACK 1,50 @4,0 + place-and-trim BACK 0,51 (parcheggio 1,00 @1000, taglio, rimpiazzo @3,95) | tutto SUCCESS; abbinati LAY 1,67, BACK 1,50 + 0,51 | PIATTA, differenza 0,009; `flatten_done` -0,05 alle 16:52:10 |
| sel 22, LAY 25 @1,65 abbinato 0,29 (17:00:29) | scavalco LAY 1,70 @1,65; chiusura BACK 2,00 @1,63 | SUCCESS | PIATTA, differenza 0,0035; `flatten_done` -0,0135 |
| sel 47973 (O/U), stesso schema | scavalco LAY 1,70 @1,84; una chiusura | SUCCESS | PIATTA, differenza 0,0016 |
| codici, sel 58805: scavalco | LAY 1,67 @4,2 | **FAILURE INVALID_BET_SIZE** (void 1,67); il bot scrive `rifiuto_taglia` CRITICAL col codice, freno 1 s | secondo scavalco LAY 1,63 @4,3 abbinato @4,2 |
| codici, sel 58805: chiusura | BACK 1,00 @3,95 diretta, poi place-and-trim di 0,97: parcheggio BACK 1,00 @1000 | parcheggio **FAILURE INVALID_PROFIT_RATIO**; il bot scrive `submin_abort ... (parcheggio rifiutato da Betfair: INVALID_PROFIT_RATIO)` (correzione di questo cantiere) | resto 0,97 dichiarato `min_bet_skip` a ogni giro di flatten finche' non scade la pausa di 30 s tra due sequenze (anti-cascata invariata) |
| codici, sel 58805: rimpiazzo | parcheggio 16:52:43 tagliato a 0,97, `replace` -> 3,65 | **FAILURE BET_TAKEN_OR_LAPSED**: nessun sostituto, parcheggio annullato | il bot scrive **«submin completato: ordine a riposo alla target_price»** (FALSO); 25 s dopo rifa' la sequenza, il rimpiazzo nasce, BACK 0,97 @3,65 abbinato @4,1 |
| codici, fine ciclo | 6 ordini dopo il primo rifiuto (tetto 10) | - | PIATTA, differenza 0,013; `flatten_done` -0,05 alle 16:53:21; nessuna posizione fantasma (RC1 e K1-K7 verdi) |

## 4. Reperti trovati durante il lavoro (tutti nel banco, corretti e falsificati)

- **R-SV1** (il controllo, non il bot), `sonda_codici_sel58805.txt`.
  - Il primo SV1 contava come «book» ogni riga del raw.
  - Il motore riemette il book di ogni mercato a ogni riga: 27 righe a 16:51:58.628 sono lo stesso book.
  - Contava anche l'orologio del banco, che avanza coi book degli ALTRI mercati.
  - Il MATCH_ODDS non pubblica nulla tra 16:51:58.628 e 16:52:07.219. Il bot chiude al primo book dopo
    la pausa: e' corretto.
  - Ora un book e' un istante di pubblicazione nuovo di QUEL mercato. Test
    `test_sv1_lo_stesso_book_riemesso_non_conta`, mutazioni C13 e C15 rosse.
- **R-BF1** (il controllo, emerso dalla falsificazione).
  - Senza scavalco il bot dichiara il residuo e RIPARTE (LAY 25 @1,64).
  - Il primo SV4 leggeva quell'ingresso come «scavalco senza attivita'».
  - Ora il primo ingresso nuovo chiude il ciclo. Test `test_ciclo_nuovo_dopo_il_residuo_non_e_uno_scavalco`
    e `test_rc2_gli_ordini_del_ciclo_dopo_non_sono_loop`, mutazione C16 rossa.

## 5. Test e falsificazioni (numeri veri)

- `python3 -m pytest Betfair/stream/tests/test_banco_uf2_parcheggio_lay_2026_10_08.py Betfair/stream/tests/test_banco_scavalco_rifiuti_2026_10_08.py -q -p no:cacheprovider`: 56 + 37 verdi.
- Test mirati dei file toccati (N3 uscite manuali e dichiarate, Applica bot x2, registro, attiva-adesso,
  sniper, certificazione scalper, i due nuovi): **492 passed, 3 skipped** (prima dell'ultimo giro di
  modifiche al modulo; la suite intera sotto li ricomprende).
- Falsificazioni (`mutazioni.txt`; sha256 del file ripristinato IDENTICO ogni volta):
  - M-UF1 (`e_parcheggio` LAY solo 1,01): 32 rossi.
  - BM-RC3 (bot, codice non letto): 1 rosso.
  - Modulo, 24 mutazioni, ognuna da 1 a 4 rossi: G1-G4 (tetto del gruppo, per ordine, guasto infinito,
    nessun riarmo), R1-R4 (codice, importo non tolto, sostituto lasciato nel Trade, tutti rifiutati),
    C1-C16 (ogni controllo e il conteggio dei book).
- **A livello di replay** (`falsificazione_replay/`, 35797769, difetto reintrodotto nel bot):
  - BF1, niente scavalco: KO, SV2 x3 (residuo 1,22 dichiarato con 0 scavalchi).
  - BF2, scavalco senza attivita': KO, SV4 x3.
  - BF4, rifiuto di taglia ignorato: KO, RC3 x2.
  - BF3, scavalco BACK dimensionato male: **OK, cioe' NON sollecitato**. Su questa registrazione tutti e
    tre i gruppi colpiti abbinano prima la gamba LAY (posizione corta): il ramo «punta 1,00» (posizione
    lunga, R4) del replay non passa mai. Limite dichiarato, sez. 8.
- Suite intera: vedi sez. 9.

## 6. Replay prima/dopo (`--worker 1`), riferimento cantiere 15

Comandi esatti:
- PRIMA: albero `git archive 3b8ce19`.
- DOPO: questo worktree.
- Registrazioni decompresse in `_live_raw` (LEGGIMI).

```
python3 -m Betfair.stream.backtest.certifica scalper_calcio <EV> --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper,uscite-manuali,uscite-manuali-firmate[,ingresso-abbinato-in-parte,ingresso-abbinato-in-parte-paper,rifiuti-betfair-codici,rifiuti-betfair-codici-paper] --worker 1 --data-dir _live_raw
```

**Confronto** con `strumenti/confronta_referti.py`, che esclude tempi, hash, percorsi e id di processo,
sui 7 scenari comuni:
- **IDENTICI** su 35797769 e su 35760084.
- L'unica riga diversa e' una riga vuota di separazione, perche' nel DOPO seguono altri scenari.

| 35797769 | PRIMA | DOPO |
|---|---|---|
| base / paper | OK 44 / OK 44 | OK 44 / OK 44 |
| chiusura-abbinata-in-parte | KO 213 (B2 0,04, decisione D1 del C15) | identico |
| rifiuti-betfair | OK 56 | OK 56 |
| sniper-paper | OK 44 | OK 44 |
| uscite-manuali | OK 239 | OK 239 |
| uscite-manuali-firmate | KO 64 (UF2: proposta 24,42, uscita 23,50) | identico |
| ingresso-abbinato-in-parte (+ -paper) | - | **OK 49 / OK 49**, impronta `b0d54620713bbd61` su 27 ordini in entrambi |
| rifiuti-betfair-codici (+ -paper) | - | **KO 132 / KO 132**, solo RC3 x1 (rimpiazzo), impronta `3fe97f9be154db71` su 30 ordini in entrambi |

**35760084**
- I 7 scenari comuni sono OK e identici.
- I 4 nuovi escono **NE**: lo scalper non apre su questa partita, il guasto non ha effetto. Lo dichiara
  la riga «NON ESERCITATO».

**UF2 di `uscite-manuali-firmate`**
- Era KO prima ed e' KO dopo, identico (KO preesistente, gia' noto al PC secondo il cantiere 15).
- **La correzione di `e_parcheggio` non cambia nessuna riga sul calcio**: nessuna uscita firmata di
  queste due registrazioni ha un parcheggio LAY a 1,02/1,03 (il caso UF2 rosso e' un parcheggio BACK
  @1000).
- La correzione e' provata solo dai test (56, M-UF1 32 rossi). Sul tennis va verificata al PC (sez. 7).

**Parita' paper/live sugli scenari nuovi**
- Stesse azioni (49/49, 132/132), stessi motivi, stesse righe di specchio.
- Impronta degli ordini identica (stessi istanti, quote, importi chiesti e abbinati, stati).

**Tempi** (parete, macchina carica):

| | PRIMA | DOPO |
|---|---|---|
| 35797769, 7 scenari comuni | 32m46s (user 15m27s) | parte dei 27m38s del DOPO (11 scenari, user 17m29s) |
| base (per scenario) | 80,7 s | 70,9 s |
| 35760084, 7 scenari | 4m22s | 2m22s |

- I 4 scenari nuovi costano 48-53 s ciascuno su 35797769 e 6 s su 35760084.
- Nei vecchi scenari la lista delle sorveglianze e' vuota: nessun costo.
- `--scenari tutti` cresce di circa 3,5 minuti di CPU per partita. Era gia' oltre il tetto prima di
  questo cantiere (riga LENTO preesistente).

## 7. Da rieseguire sul PC (registrazioni tennis assenti nel cloud)

`e_parcheggio` e' del banco COMUNE: riguarda le uscite firmate dei 4 bot tennis.

Comando, PRIMA (commit `3b8ce19`) e DOPO, sulle due registrazioni di riferimento:

```
python -m Betfair.stream.backtest.certifica <tennis_scalper|tennis_pro|tennis_flb|tennis_swing> 35790089 35794049 --scenari uscite-manuali,uscite-manuali-firmate --worker 1 --data-dir <tennis_rec\giorno>
```

- Atteso: referti identici, oppure differenze SOLO nelle righe UF2 / «USCITE MANUALI ... non giudicabili».
- Una differenza e' spiegata dalla correzione se l'uscita firmata ha un parcheggio LAY a 1,02/1,03, cioe'
  un resto 0,50-0,79 (cantiere 5). In quel caso UF2 ora aspetta la catena e aggancia il rimpiazzo.
- Ogni altra differenza = cantiere fermo.

Scalper calcio sul PC: lo stesso comando della sez. 6 sulle due partite. Atteso, numero per numero:
- i 7 scenari comuni come il cantiere 15;
- `ingresso-abbinato-in-parte*` OK 49;
- `rifiuti-betfair-codici*` KO 132 con solo RC3 x1 sul rimpiazzo;
- 35760084: i 4 nuovi NE.

## 8. Limiti dichiarati / cosa NON ho verificato

- **Sniper**:
  - gli scenari nuovi girano col solo maker (`sniper_mode` False come `base`);
  - lo scavalco e il tetto dello sniper sono coperti dai test del 07/10, NON da un replay del banco;
  - stesso difetto RC3 in `sniper_bot.py:1322`, non toccato.
- **Ramo «punta 1,00» dello scavalco** (posizione lunga, reperto R4): non esercitato da questi replay
  (BF3 verde). Tutti i gruppi colpiti su 35797769 abbinano prima la LAY.
- **SV5 (loss_cap)**:
  - mai sollecitato nei replay, sono «non lo so» e lo dice il referto;
  - con i parametri di serie, e con il minimo non nullo della UI (0,50, `lib/scalper.ts`), queste perdite
    di 1-5 centesimi per ciclo non arrivano al tetto;
  - coperto solo dai test (3 casi, mutazioni C10 e C14 rosse);
  - non ho aggiunto uno scenario «cap stretto» con un valore che la UI non permette.
- **La copertura SV/RC non e' nella tabella COPERTURA DEI CONTROLLI** di `certifica.py` (fuori
  perimetro).
  - Sollecitazioni e «MAI sollecitati» stanno nelle note del referto di ogni scenario.
- **Il finto Betfair rifiuta solo il primo ordine di ogni tipo.**
  - Non provati: i rifiuti ripetuti, il taglio rifiutato (cancelOrders), `INVALID_PROFIT_RATIO` sul
    rimpiazzo.
- **RC2**: conta gli ordini fino al primo ingresso nuovo. Un ingresso nato nel giro stesso del rifiuto
  (meno di 1 s) puo' sfuggire al taglio.
- **Tennis**: nessun replay (sez. 7).
- **DB**: nessun DB.
- **Frontend**: non toccato; ne' vitest ne' tsc lanciati.

## 9. Suite

`python3 -m pytest Betfair/ -q -p no:cacheprovider` (DOPO, `pytest_betfair_dopo.txt`): **11049 passed,
64 skipped, 6 xfailed, 0 failed** in 6m55s (14 avvisi preesistenti di thread nei test del battito tennis).
Il rosso di latenza `<20 ms` visto dal cantiere 15 qui non e' comparso (macchina meno carica).

## 10. Decisioni per l'utente

- **D1 - Rimpiazzo rifiutato da Betfair: il bot dice «a riposo» un ordine che non esiste.**
  - Fatto (RC3 rosso, `traccia_codici_sel58805.txt` 16:52:47): con `replaceOrders` rifiutato,
    `trading/submin.advance_submin` passa REPRICED -> DONE senza guardare se il sostituto e' nato.
    Il bot scrive «submin completato» e per circa 25 s crede chiuso cio' che non lo e'.
  - Il codice non arriva a nessuno: `flumine/execution/betfairexecution.py`, ramo FAILURE del place di
    `execute_replace` = `pass  # todo`.
  - Sul banco la posizione si chiude comunque, ma in ritardo.
  - Proposta: dopo il replace la sequenza resta in attesa finche' il sostituto non compare nel `Trade`.
    Se il replace e' eseguito e il sostituto non c'e', riga `submin_abort` «rimpiazzo NON nato
    (replaceOrders rifiutato; codice non restituito)» e la chiusura si rifa'.
  - Tocca `trading/submin.py`, che e' condiviso da scalper, sniper, tennis e worker: e' una decisione
    del coordinatore/utente, NON fatta.
  - Finche' non e' decisa, `rifiuti-betfair-codici*` resta KO con quella sola riga: e' il banco che dice
    la verita'.
- **D2 - Stessa riga senza codice nello sniper e nello scalper tennis.** `sniper_bot.py:1322` e
  `tennis_scalper_bot.py:2850`: la stessa correzione di una riga del maker. Non fatta: non e' dimostrata da
  un replay di questi bot.
- **D3 - Resto 0,97 dopo un parcheggio rifiutato.** Il flatten scrive `min_bet_skip` a ogni giro (79
  righe) finche' non scade la pausa anti-cascata di 30 s fra due sequenze. Condotta di sempre, limitata e
  dichiarata; sono 30 s scoperti di 0,97. Cambiare la pausa e' una decisione di trading: non fatto.
- Le decisioni aperte del cantiere 15 (D1 B2 per ciclo) restano dove sono: `chiusura-abbinata-in-parte`
  e' KO identico, NON corretto (ordine del coordinatore).

## 11. Da controllare dal vivo in PROVA

Dopo un rifiuto di Betfair su un parcheggio dello scalper, l'attivita' `submin_abort` porta «(parcheggio
rifiutato da Betfair: <CODICE>)» e il campo `codice` (pagina Scalper, attivita').

## Blocco per la cronostoria

```
### 08/10 - Cantiere 9 (scalper calcio: scavalco, rifiuti coi codici, reperto 7.2 del C5) - delegato cloud
- Banco: nuovo `backtest/scavalco_rifiuti.py` (guasto «ingresso abbinato in parte», max 0,29 per
  gruppo, e finto Betfair coi codici veri INVALID_BET_SIZE / INVALID_PROFIT_RATIO / BET_TAKEN_OR_LAPSED
  su scavalco, parcheggio e rimpiazzo). Controlli SV1-SV5, RC1-RC4 dal mercato. 4 scenari nuovi
  (+ -paper), aggancio additivo in scalper/tools/replay_registrazioni.py, classificati in applica_bot.
- Reperto 7.2 C5 corretto: uscite_manuali.e_parcheggio riconosce LAY 1,01-1,03
  (condotta_ordini.QUOTE_PARCHEGGIO_LAY, fonte unica). Nessuna riga cambiata sul calcio; tennis da
  rifare sul PC.
- Bot: scalper_bot._drive_submins scrive il codice del parcheggio rifiutato (RC3, una riga di telemetria;
  test + mutazione BM-RC3).
- Replay --worker 1 PRIMA/DOPO: 7 scenari comuni IDENTICI su 35797769 e 35760084. Nuovi su 35797769:
  ingresso OK 49 (3 scavalchi, 3 cicli piatti), codici KO 132 (solo RC3: rimpiazzo rifiutato, il bot
  dice «a riposo»); paper = live, stessa impronta. 35760084: nuovi NE.
- Falsificazioni: M-UF1 32 rossi, BM-RC3 1, modulo 24/24, replay BF1/BF2/BF4 KO (BF3 non sollecitata:
  ramo punta 1,00 mai visto).
- Decisioni aperte: D1 (rimpiazzo rifiutato, submin.py condiviso), D2 (sniper/tennis stessa riga),
  D3 (pausa 30 s dopo un parcheggio rifiutato).
- Punto di ripresa: decidere D1; rifare sul PC i replay tennis di uscite-manuali(-firmate) e quelli della
  sez. 6. Referto: AUDIT_2026-10-08/cantiere_9/REFERTO.md
```

## Verifica del coordinatore cloud (08/10)
- Diff riletto: `e_parcheggio` dalla fonte unica (BACK 1000, LAY `QUOTE_PARCHEGGIO_LAY` 1,01-1,03); `scalper_bot.py` solo telemetria
  (codice del rifiuto nella riga `submin_abort`, nessuna decisione cambiata); scenari e controlli nuovi in un modulo nuovo.
- Test: i due file nuovi 93/93 nel checkout integrato. MIA MUTAZIONE: parcheggio LAY riconosciuto solo a 1,01 -> 33 rossi.
- MIO REPLAY (`verifica_coordinatore_35797769.txt`): `ingresso-abbinato-in-parte` OK 49 azioni, `rifiuti-betfair-codici` KO RC3 132
  azioni: IDENTICI al referto del delegato.
- DIFETTO APERTO MONEY-CRITICAL (D1, non corretto qui: tocca `trading/submin.py`, condiviso da scalper, sniper, bot tennis e worker):
  dopo un `replaceOrders` RIFIUTATO `advance_submin` passa a DONE e il bot crede chiusa per ~25 s una posizione che non lo e'; il
  codice d'errore non arriva (flumine `execute_replace`: `pass # todo`). Da decidere con l'utente come cantiere a se', certificato su
  tutti i bot che usano il place-and-trim.
