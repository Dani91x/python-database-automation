# W2 / D-7 - ANNULLO AUTOMATICO DELL'ORDINE DELL'APP NELLA CHIUSURA DEGLI ORDINI DEL SITO

Data: 08/10/2026 sera (ore dall'orologio: inizio ~20:40, fine 21:05). Delegato Opus.
Worktree `C:\Users\Admin\Desktop\PYTHON DATABASE\wt-w2`, ramo `cantiere-w2-sera` da master
`d257abea`, junction a `.venv` e `frontend\node_modules` del principale (NON smontato).
Nessun commit, nessun `git add`, nessun ordine su Betfair, nessun processo nuovo, nessun file
del checkout principale toccato.

## 1. La decisione e che cosa c'era

Decisione dell'utente D-7 ("annullarlo") sul punto 3 del par. 8 di
`AUDIT_2026-10-08/W2_CHIUSURA_ORDINI_SITO.md`. Prima: nel `greenup` con
`params.esposizione='fuori_bot'` un ordine DELL'APP (`customerStrategyRef` 'live', classificato
fuori bot) ancora `EXECUTABLE` con `sizeRemaining > 0` sul lato della copertura faceva RIFIUTARE
il comando ("nessun secondo ordine (annullarlo o attendere)").

Adesso, nello stesso punto:
1. si ANNULLANO quegli ordini (solo quelli: app, fuori bot, lato della copertura, non abbinati)
   con `cancelOrders` del client REALE della riga, sincrono, con `marketId` e i loro `betId`;
2. si RILEGGE il conto (`listCurrentOrders`, stessa funzione di prima) e si ricalcola TUTTO
   (classificazione, esposizione, mercato a due esiti, piano) sull'esposizione REALE;
3. se dopo la rilettura un ordine dell'app e' ancora vivo sul lato della copertura (annullo
   rifiutato, rete giu', esito "SUCCESS" ma ordine ancora li') -> RIFIUTO, nessuna copertura;
4. se nel frattempo l'ordine si e' abbinato in tutto o in parte, la copertura e' quella della
   parte vera (o nessuna, se la posizione e' diventata piatta);
5. l'esito DICHIARA l'annullo: chiave additiva `result.annullati_app`
   (`[{bet_id, side, price, non_abbinato, size_annullata, esito: 'annullato'|'fallito', errore}]`)
   e il testo dell'annullo IN TESTA al `detail` (o all'errore), cosi' il troncamento a 300 non lo
   taglia; se a fallire e' il piazzamento della copertura dopo l'annullo, l'errore resta quello di
   sempre in testa (codici, `post_place:`) e l'annullo e' detto IN CODA, stesso tipo di eccezione.

Invariato: gli ordini degli altri bot (anche `live` dalla coda del runner) non sono fuori bot e
non si guardano ne' si toccano (classificazione W2/W3a intatta); gli ordini del SITO appesi non
si annullano e non fermano (come prima); un ordine dell'app appeso sul lato OPPOSTO non si tocca;
a posizione gia' piatta non si annulla niente. Senza ordini dell'app appesi sul lato della
copertura il ramo fa esattamente le stesse chiamate di prima (una `listCurrentOrders`, nessuna
`cancelOrders`) e scrive la stessa riga (differenziale, par. 4).

## 2. Diff (solo `Betfair/stream/live_order_worker.py`, +219/-65; CRLF conservati, ASCII-only)

| righe (worktree) | cosa |
|---|---|
| 2342-2483 (nuove) | `_efb_posizione`: le righe "1) conto" e "2) due esiti + piano" di `_do_greenup_fuori_bot` SPOSTATE senza cambiarne una (stessi messaggi d'errore), per poterle rieseguire. `_efb_app_appese`: il filtro di prima (csr 'live' + EXECUTABLE + residuo > 0 + lato), ora funzione. `_efb_annulla_app`: il `cancelOrders` (guardia MONEY-CRITICAL: mai senza `marketId` o senza `betId`, perche' Betfair annullerebbe tutto il mercato o tutto il conto; `lightweight=True` -> dict; non solleva, l'esito per ordine finisce in `errore`; a decidere e' la rilettura). `_efb_nota_annullo`: il testo. |
| 2492-2501 | docstring: il rifiuto per "copertura appesa" diventa "ordine dell'app che resta vivo dopo l'annullo"; import `altro_runner_due_esiti`/`compute_greenup` spostati in `_efb_posizione`. |
| 2541-2576 | corpo: `pos = _efb_posizione(...)`; se il piano e' eseguibile e ci sono ordini dell'app appesi sul suo lato -> annullo, log WARNING, rilettura (KO -> errore con l'annullo in testa), controllo "ancora vivo" -> rifiuto; poi le variabili di sempre da `pos`; `testa` = nota dell'annullo o "". |
| 2582-2591 | `extra["annullati_app"]` solo se c'e' stato annullo; `testa` davanti al rifiuto "NON eseguibile" e al `detail` "gia' piatta". |
| 2596 (tolte 14 righe) | il vecchio rifiuto "copertura dell'app appesa" (sostituito dal punto sopra). |
| 2610 | `testa` davanti al rifiuto "CHIUSA DALL'UTENTE". |
| 2619-2639 | piazzamento in `try`: con annullo gia' fatto un `ValueError`/`RuntimeError` del piazzamento si rilancia dello STESSO tipo con `[prima: annullo automatico ordini dell'app <bet_id>]` in coda; senza annullo `raise` nudo (identico a prima). |
| 2646 | `testa` davanti al `detail` della copertura piazzata. |

Perche' `cancelOrders` REST e non `market.cancel_order` di flumine: (1) l'ordine dell'app puo'
non essere nel blotter del runner (riavvio; il ramo infatti legge il conto da REST e non dal
blotter); (2) l'annullo di flumine e' asincrono, non si saprebbe se e quanto e' stato annullato
prima di ricalcolare. Il client e' lo stesso REALE della `listCurrentOrders` della riga.
`live_order_worker.py` e' gia' nel contratto "strada unica" (`test_contratto_strada_unica_
2026_09_25.py`, controllo per FILE: verde), ma il suo `motivo` parla solo di `market.place_order`:
**da decidere se aggiornarne il testo** ("cancelOrders REST del ramo fuori bot, D-7") - NON l'ho
toccato (e' una riga di contratto, decisione dell'utente/coordinatore).

## 3. Test

### 3.1 Nuovo file `Betfair/stream/tests/test_greenup_fuori_bot_annullo_app_2026_10_08.py` (20 casi)

Finti: quelli del W2 importati dal suo file (client VERO di flumine + `APIClient` VERO con il solo
trasporto sostituito, `MarketBook` VERO, tabelle con le colonne vere). Il trasporto risponde in piu'
a `SportsAPING/v1.0/cancelOrders` col JSON di Betfair (`status`, `marketId`, `errorCode`,
`instructionReports[{status, errorCode, instruction{betId}, sizeCancelled, cancelledDate}]`) e,
come Betfair, CAMBIA lo stato dell'ordine sul conto; la forma e' provata costruendo la classe
VERA `CancelOrders` di betfairlightweight su ogni risposta.

| criterio | test | che cosa prova |
|---|---|---|
| (a) | `test_a_ordine_dell_app_appeso_si_annulla_poi_si_copre_e_l_esito_lo_dice` | chiamate `[list, cancel, list]`; cancel con `marketId` della riga e SOLO `betId` H1; nessun piazzamento prima dell'annullo; copertura LAY 6,00 @2,5 (quella del sito); `annullati_app` esatto; `detail` che inizia con l'annullo |
| (a) | `test_a_la_risposta_del_finto_e_quella_della_libreria_vera` | le 4 forme di risposta del finto passano dalla classe vera `CancelOrders` |
| (b) | `test_b_annullo_fallito_nessuna_copertura_e_il_motivo` x3 (FAILURE `ERROR_IN_ORDER`; rete giu'; "SUCCESS" ma ordine ancora vivo) | nessun ordine, riga `error` che inizia con "ordine dell'app H1 LAY ancora non abbinato (6.0) dopo l'annullo: nessuna copertura; annullo automatico ..." col motivo, < 300 caratteri |
| (b) | `test_b_annullo_riuscito_ma_conto_non_rileggibile_nessuna_copertura` | mai una copertura su esposizione vecchia: rilettura KO -> nessun ordine, errore con l'annullo in testa e "conto non leggibile" |
| (c) | `test_c_abbinato_in_parte_durante_l_annullo_copertura_sulla_parte_vera` | 2 dei 6 si abbinano durante l'annullo: W 7 / L -3 -> LAY 4,00 (non 6,00); `size_annullata` 4; testo "annullato 4.00, 2.00 abbinato nel frattempo" |
| (c) | `test_c_abbinato_tutto_prima_dell_annullo_posizione_piatta_nessun_ordine` | `BET_TAKEN_OR_LAPSED`: riletto, W = L = 1 -> nessuna seconda copertura, `done` "gia' piatta" con l'annullo fallito dichiarato |
| (c) | `test_c_annullo_fatto_poi_il_mercato_si_sospende_l_errore_dice_dell_annullo` | book vuoto dopo l'annullo: rifiuto "NON eseguibile" con l'annullo in testa |
| (c) | `test_c_annullo_fatto_poi_la_copertura_e_rifiutata_l_errore_dice_dell_annullo` | `place_order` False: testa dell'errore di sempre, annullo in coda |
| (c) | `test_c_annullo_fatto_poi_la_copertura_chiuderebbe_mike_rifiuto_che_lo_dice` | il caso W2 "chiuderebbe Mike" con in piu' un LAY dell'app appeso: annullo, poi lo stesso rifiuto di prima con l'annullo in testa |
| (d) | `test_d_ordini_non_abbinati_degli_altri_bot_non_si_toccano` | Omega dalla coda (csr 'live', bet_id in `omega_trades`) e Mike REST non abbinati sul lato della copertura: nessun `cancelOrders`, copertura come prima |
| parita' | `test_senza_ordini_dell_app_sul_lato_della_copertura_nessun_annullo` x2 (sito appeso sul lato; app appesa sul lato opposto) e `test_posizione_piatta_con_ordine_dell_app_appeso_nessun_annullo` | una sola `listCurrentOrders`, nessun annullo |
| errori | `test_senza_annullo_l_errore_del_piazzamento_e_quello_di_sempre` | senza annullo nessuna coda nel testo |
| guardie | `test_mai_cancel_orders_senza_mercato_o_senza_bet_id` x3, `test_esito_senza_report_per_l_ordine_e_un_fallimento` | mai `cancelOrders` senza mercato o betId; report mancante = fallito |

### 3.2 I test esistenti del W2: NON modificati

`test_greenup_fuori_bot_2026_10_08.py` (oggi **58** casi: 56 del W2 + 2 aggiunti da W3a; sha256
`680985b7...329e` identico a master) **58 passed** senza modifiche. Uno solo cambia SIGNIFICATO,
non esito: `test_copertura_dell_app_ancora_appesa_sul_lato_della_copertura_ferma_il_secondo`. Il
suo conto finto (il `Conto` del W2) non sa rispondere a `cancelOrders` (risponde con la forma di
`listCurrentOrders`): per il worker nuovo e' "annullo FALLITO: risposta inattesa", la rilettura
trova l'ordine ancora vivo e il comando e' rifiutato senza ordini - quindi le sue due asserzioni
(`status == 'error'`, nessun ordine, "ancora non abbinato" nel testo) restano vere, ma ora provano
il caso (b) "annullo fallito", non piu' il rifiuto senza tentativo. Il comportamento con l'annullo
riuscito e' nel file nuovo. Riga per riga del differenziale (par. 4): stesse letture del conto
+ `cancelOrders` + seconda lettura; stesse 5 letture DB ripetute alla rilettura; testo dell'errore
nuovo.

### 3.3 Suite

- `pytest test_greenup_fuori_bot_annullo_app_2026_10_08.py test_greenup_fuori_bot_2026_10_08.py
  -p no:cacheprovider` -> **78 passed** (20 + 58).
- `pytest Betfair/stream/tests Betfair/stream/tennis_live/tests Betfair/omega/test_omega_flumine_live.py
  Betfair/safe_strategy/tests/test_riconciliazione_tradotti_safe_2026_10_02.py
  Betfair/safe_strategy/tests/test_soldi_veri_catena_2026_10_04.py -q -p no:cacheprovider -n 3`
  (tutti i file di test che importano il worker + `Betfair/stream/tests`) -> **5482 passed, 56 skipped,
  5 xfailed, 0 failed** in 324 s (corsa normale, 20:57-21:03). Comprende la parita' a 51 scenari, il
  contratto strada unica, follow-through, cash-out, reconcile.
- Frontend: nessun file toccato. `npx vitest run src/pages/CashOut.test.tsx` -> 21 passed (sanita',
  codice invariato). tsc non rilanciato (nessun .ts toccato).

## 4. Parita' (differenziale) e 51 scenari

`AUDIT_2026-10-08/decisioni_sera/W2_D7_strumenti/differenziale_d7.py` + `cattura_plugin.py`: il
file di test del W2 eseguito col worker di `master` (messo con `git show`, poi rimesso il nuovo e
verificato sha256 `d4056041f55e4f32...edc3`) e col worker D-7, registrando a OGNI `esegui` la riga di
coda (senza `processed_at`), gli ordini piazzati (lato, prezzo, size, persistenza, ref di
strategia), i metodi chiamati sul conto, le letture del DB, le letture del blotter.
Esito (`uscite/differenziale.txt`): master 58 passed, D-7 58 passed; **46 test, 47 comandi, 1
diverso**: il test della copertura appesa (spiegato al 3.2). Tutti gli altri identici campo per
campo. Il test dei **51 scenari** del green-up di sempre (`test_parita_byte_per_byte_con_il_greenup
_di_b5547eb`) e' verde in entrambe le corse: il ramo di sempre non e' toccato (il diff e' tutto
dentro `_do_greenup_fuori_bot` e nelle funzioni nuove).

## 5. Falsificazione (`W2_D7_strumenti/falsifica_d7.py`, uscita `uscite/falsificazione.txt`)

Ogni mutazione applicata al worker, rilanciati i 2 file (78 casi), ripristino dai byte originali
con sha256 verificato dopo OGNI mutazione e alla fine (`d4056041...edc3`), 78 passed dopo il
ripristino.

| # | mutazione | rossi |
|---|---|---|
| D1 | nessun annullo, si copre comunque | 12 |
| D2 | nessuna rilettura dopo l'annullo | 10 |
| D3 | nessun controllo "ancora vivo" dopo la rilettura | 4 |
| D4 | `cancelOrders` senza `betId` (tutto il mercato) | 11 |
| D5 | guardia mercato/betId tolta | 3 |
| D6 | annullo anche degli ordini 'live' dei BOT | 1 |
| D7 | lato della copertura ignorato | 1 |
| D8 | annullo non dichiarato nel detail | 5 |
| D9 | `annullati_app` non nell'esito | 3 |
| D10 | `sizeCancelled` ignorata | 1 |
| D11 | `SUCCESS` letto come fallito | 6 |
| D12 | rilettura KO senza la nota dell'annullo | 1 |
| D13 | `lightweight=True` tolto (risposta risorsa) | 9 |
| D14 | errore del piazzamento senza la coda dell'annullo | 1 |
| D15 | coda dell'annullo anche SENZA annullo | 1 |
| D16 | ordini del SITO annullati come quelli dell'app | 2 |
| D17 | annullo anche a posizione piatta | 1 |
| D18 | rifiuto "NON eseguibile" senza la nota | 1 |
| D19 | rifiuto "CHIUSA DALL'UTENTE" senza la nota | 1 |

**19 mutazioni, 19 rosse, 0 non catturate.**

## 6. A schermo (pagina Cash Out)

Nessuna modifica al frontend necessaria: `ScatolaCashOut.greenupFuoriBot` mostra `r.detail` sulla
riga eseguita e `r.error` sulla rifiutata (`TESTO_FASE[fase]: motivo`, `co-fuori-bot-esito` e
`co-posizione-conto-esito`), e `sendLiveOrderCommand` porta `result` (done) ed `error` (error) della
riga di coda. Il testo dell'annullo e' in TESTA a entrambi. Esempi veri (dai test):
- eseguita: "annullo automatico ordine dell'app: H1 LAY @2.60 (6.00 non abbinato) annullato 6.00;
  esposizione riletta dal conto; LAY 6.00@2.5 (f=1.00); atteso vince=1.0 perde=1.0; conto: ..."
- abbinata in parte: "... annullato 4.00, 2.00 abbinato nel frattempo; esposizione riletta dal conto; LAY 4.00@2.5 ..."
- rifiutata: "greenup fuori_bot: ordine dell'app H1 LAY ancora non abbinato (6.0) dopo l'annullo:
  nessuna copertura; annullo automatico ordine dell'app: H1 LAY @2.50 (6.00 non abbinato) annullo
  FALLITO: cancelOrders FAILURE: ERROR_IN_ORDER; esposizione riletta dal conto"
NON verificato nel browser. Nota UI (fuori perimetro, non fatta): la doppia conferma del pulsante
non PREANNUNCIA che un ordine dell'app appeso sara' annullato; lo dice solo l'esito.

## 7. Da controllare dal vivo (LIVE, primo uso)

1. Ordine del sito abbinato + un ordine dell'app (ladder) non abbinato sul lato della copertura,
   stessa selezione calcio seguita: "chiudi" dalla pagina -> sul conto Betfair l'ordine dell'app
   risulta ANNULLATO (pagina "ordini" del sito) e c'e' UNA sola copertura nuova; riga di coda `done`
   con `result.annullati_app[0].esito='annullato'` e `size_annullata` = non abbinato visto.
2. Nel log del runner: `[live-order] greenup fuori_bot riga <id>: annullo automatico ...` (WARNING).
3. Ordine dei bot (Mike/Omega/Safe) non abbinato sulla stessa selezione: resta sul mercato.
4. Tempo fra `requested_at` e `processed_at`: ora contiene 2 `listCurrentOrders` + 1 `cancelOrders`
   (tutto dentro `LUCCHETTO_ORDINI`, gli altri ordini aspettano).
5. Il blotter del runner, se l'ordine dell'app era suo: lo vede `EXECUTION_COMPLETE` (dallo stream
   ordini) e il follow-through della riga che lo aveva piazzato lo chiude come "ok" senza
   ri-coprire (codice letto, non provato dal vivo).

## 8. Che cosa NON ho verificato

- Nessuna chiamata vera a `cancelOrders`/`listCurrentOrders`: forma da libreria (classe
  `CancelOrders`) e documentazione; il codice `BET_TAKEN_OR_LAPSED` per l'ordine abbinato nel
  frattempo e' quello documentato da Betfair, non osservato qui.
- Che Betfair, dopo un `cancelOrders` SUCCESS, mostri SUBITO l'ordine come non piu' EXECUTABLE in
  `listCurrentOrders` (consistenza immediata): se la rilettura lo vedesse ancora vivo, il comando
  e' RIFIUTATO (prudente, provato dal caso "muto"), l'utente ripremera'.
- Il follow-through di una riga precedente la cui copertura viene annullata da D-7: letto
  (`EXECUTION_COMPLETE` -> ok, nessun re-hedge), non provato da un test.
- Nessun replay: il ramo e' solo LIVE con client reale e il banco gira su client simulati
  (stessa causa del W2, par. 5); i bot non passano da questo ramo.
- Il testo del contratto "strada unica" non e' aggiornato (par. 2).
- Browser: non aperto.

## 9. Blocco pronto per `CRONOSTORIA.md` (non scritto li')

> **W2/D-7 (08/10 sera, delegato Opus, worktree `wt-w2` ramo `cantiere-w2-sera` da `d257abea`,
> non committato)** - Decisione dell'utente "annullarlo": nel green-up FUORI BOT un ordine
> dell'APP non abbinato sul lato della copertura non ferma piu' il comando: si annulla
> (`cancelOrders` REST del client reale, solo i suoi `betId`, mai senza mercato/betId), si
> rilegge il conto e si copre l'esposizione REALE (abbinato in parte -> copertura sulla parte
> vera; abbinato tutto -> piatta, nessun ordine); annullo fallito/ordine ancora vivo -> rifiuto,
> nessuna copertura; esito con `annullati_app` e l'annullo in testa a `detail`/errore. Ordini
> dei bot, del sito e dell'app sul lato opposto: non toccati. File: `live_order_worker.py`
> (+219/-65, lettura spostata in `_efb_posizione` senza cambiarla), test nuovo
> `test_greenup_fuori_bot_annullo_app_2026_10_08.py` (20 casi, 19 mutazioni tutte rosse). I 58
> test del W2 verdi SENZA modifiche (uno cambia significato: ora prova l'annullo fallito);
> differenziale master/D-7 sui 47 comandi del W2: 1 diverso (quello), 51 scenari verdi.
> Suite stream + tennis_live + omega/safe che importano il worker: 5482 passed, 0 failed.
> Referto `AUDIT_2026-10-08/decisioni_sera/W2_D7_ANNULLO_ORDINE_APP.md`. Aperto: testo del
> contratto strada unica per il `cancelOrders` del worker; prova dal vivo par. 7.
> Ripresa: il coordinatore rilegge il diff, rilancia test, differenziale e falsificazione.
