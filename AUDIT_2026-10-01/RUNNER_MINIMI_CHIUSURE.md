# RUNNER_MINIMI_CHIUSURE - minimi .it senza esenzioni per le chiusure (01/10/2026)

Delegato Opus. Worktree da master `aa5749a` (il worktree era su `ebfab2a`: portato a
`aa5749a` con fast-forward, nessun commit). Niente commit, niente DB, nessun ordine vero.
Consegna:
- `RUNNER_MINIMI_CHIUSURE.patch`: `git diff aa5749a` piu' i 3 file nuovi, 39 file e 4167 righe. Master oggi e' a `569d633`, ma dopo `aa5749a` ha solo commit di docs: nessun file sotto `Betfair/` e' toccato, quindi la patch si applica;
- questo referto;
- `RUNNER_MINIMI_CHIUSURE_xfail.txt`;
- `RUNNER_MINIMI_REPERTO_3_DIVERGENZA_STRATEGIA.md`, da portare all'utente;
- `falsifica_runner_minimi.py` con il suo `_out.txt`;
- `replay/*_RUNNER_MINIMI.txt`.

## 0. Stato in una riga

Il motore ordini del runner non manda piu' a Betfair un ordine sotto il minimo .it, chiusure
comprese. Sotto il minimo prova, in quest'ordine: l'equivalente sull'altra selezione, poi il
place-and-trim; se nessuno dei due e' possibile rifiuta esplicitamente.

- **Suite ufficiale** (`Betfair/stream/tests Betfair/safe_strategy Betfair/omega`) piu'
  tennis e Mike: **9089 passed, 0 failed, 9 xfailed** (8 del reperto 1 e uno che c'era gia').
- **`Betfair/` intera**: 9221 passed e 9 xfailed. Resta **1 rosso che c'e' gia' su master**,
  verificato su un export pulito di `aa5749a`: `omega/tests/test_ref_strategia_per_attore_
  r1::test_omega_piazza_con_omega_come_prima`. Fallisce solo quando gira dopo `Betfair/mike`,
  perche' un test di Mike lascia sporco un ref di strategia globale; da solo e nella suite
  ufficiale e' verde. Ce n'e' poi uno dipendente dall'ordine, anche questo gia' su master:
  `safe_strategy/tests/test_audit::test_l4_la_guardia_combo...`. Da solo fallisce anche su
  master; nelle suite intere e' verde.
- **Riallineamento dei test**: i 121 test che codificavano i minimi superati (punta 2,00 col
  passo 0,50, banca 0,50, porta-al-minimo del tennis a 2,00) sono stati RIALLINEATI. Ho
  cambiato solo i numeri del listino, e in ogni file c'e' la riga di motivo «minimi .it
  definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50».
- **Xfail del reperto 1**: le CONDOTTE diventate impossibili per legge (chiusure esatte con
  resto sotto 0,50, nei bot tennis) sono xfail col motivo `XFAIL_REPERTO_1`, par. 8.
- **Comportamento dei bot**: nessun bot cambia comportamento per far passare un test.
- **Test nuovi e falsificazione**: i 21 test nuovi sono verdi; rifatta dopo il
  riallineamento, le 8 mutazioni sono ancora tutte rosse.
- **Replay**: Omega e Safe sono identici ai referti precedenti. I due profili rapidi sulla
  registrazione vera sono verdi (`safe_base` e `safe_tennis`, scenario R8).

## 1. La causa

`live_order_build.min_stake_rules` (master, righe 157-159) restituiva `valid=True` per
qualunque size quando `reduces_liability=True`. L'ipotesi «Betfair accetta le chiusure sotto
il minimo» e' FALSA: nessuna fonte la sostiene, e oggi una banca da 0,43 @18 di Mike e' stata
rifiutata `INVALID_BET_SIZE` 21 volte. Il flag lo mettono:
- `safe_strategy/execution.py`, sulle chiusure;
- `omega/porta_ordini.py:124`;
- `mike/porta_ordini.py:107`;
- `motore_ordini.valida_comando` per ogni comando con `reduces_liability`;
- greenup e cash-out del worker.

C'era poi un secondo difetto: la punta veniva legalizzata PER DIFETTO ai multipli di 0,50
(`_floor_to_step`), e restavano scoperti fino a 0,49 EUR.

## 2. Le regole applicate (decisioni del coordinatore, recepite)

UNA definizione per tutto il repo: `Betfair/stream/trading/minimi_it.py` (nuovo, senza
dipendenze). I nomi sono quelli chiesti, cosi' li puo' importare anche il delegato di Mike:
- `IT_MIN_BACK = 1.00`, `IT_MIN_LAY = 1.00`: ordine DIRETTO, al centesimo, nessun passo di
  0,50. Per la banca conta il size (la puntata del backer), mai la liability.
- `SUBMIN_IMPORTO_FINALE_MIN = IT_FLOOR_LEGGE = 0.50`: importo FINALE minimo di un
  place-and-trim. Il parcheggio resta >= 1,00 (e' un ordine diretto).
- Sotto 0,50 nessun ordine, mai.

La distinzione «diretto 1,00 / finale del trim 0,50 / mai sotto» e' scritta accanto alla
costante.

Le fonti stanno in `RICERCA_STAKE_MINIMI_BETFAIR.md` e `RICERCA_TOOL_ITALIA_STAKE_MINIMI.md`:
Nota informativa betfair.it, blog betfair.it del 30/10/2023, DM 47/2013 art. 8.

- `IT_PASSO_PUNTA_RIPIEGO = 0.50` serve SOLO all'unico ripiego dopo un `INVALID_BET_SIZE`
  reale.
- `reduces_liability` resta SOLO come informazione (`order.context` per i control di flusso,
  note, diario).

Come ho recepito le tre correzioni in corso d'opera:
- **Prima correzione: banca 1,00, punta 2,00, trim >= 1,00.** Superata dalla terza.
- **Seconda correzione: perimetro.** Ho scelto l'opzione (B). La guardia sta solo sulle
  strade del motore ordini; avevo aggiunto una guardia nel nucleo `advance_submin` e l'ho
  TOLTA.
- **Terza correzione: punta e banca 1,00, finale del trim 0,50.** Applicata.

Ordine del verdetto (`live_order_build.verdetto_minimi`, pura):
1. `diretto`: size >= minimo.
2. `equivalente`: mercato a 2 esiti, equivalente piazzabile diretto, nessun esito peggiore
   del chiesto oltre 0,01, vincita sotto il massimo.
3. `submin`: importo >= 0,50 ed esecutore col place-and-trim. Il tennis non ce l'ha.
4. `impossibile`: motivo che comincia con `SOTTO_MINIMO_NON_PIAZZABILE` e residuo «da
   dichiarare al trader (lasciarlo, oppure aumentare e richiudere)».

Il motivo del place-and-trim dichiara il bet delay doppio in gioco: circa da 5 a 10 s nel
calcio.

Equivalente: `lay X S@q == back Y S(q-1) @ q/(q-1)`, e simmetrico per la punta. La quota si
arrotonda dal lato che non peggiora mai il limite chiesto: punta equivalente al tick in su,
banca equivalente al tick in giu'. La size copre esatto l'esito sfavorevole del chiesto.

## 3. Le modifiche, file per file

| file | cosa |
|---|---|
| `stream/trading/minimi_it.py` (nuovo) | le costanti uniche (par. 2) |
| `stream/live_order_build.py` | importa da `minimi_it`, con gli alias storici `IT_BACK_MIN_STAKE`/`IT_LAY_MIN_SIZE`/`IT_BACK_STEP`; `min_stake_rules` (r. 175) senza esenzione e al centesimo; nuove `size_ripiego_punta` (234), `punta_da_sorvegliare_per_ripiego`, `equivalente_lato_opposto` (296), `riporta_abbinato_all_originale` (342), `verdetto_minimi` (407); `build_order` senza esenzione (solleva `SOTTO_MINIMO_NON_PIAZZABILE` prima di qualunque invio), con `simulato_ammette_sotto_minimo` usato SOLO dalle gambe greenup/cash-out in PAPER (comportamento di sempre: sequenza sincrona impossibile sul simulato) |
| `stream/motore_ordini.py` | `_applica_minimi` (r. 1104) su OGNI place, aperture e chiusure, idempotente col ripristino `_ripristina_minimi` all'inizio di `_controlla`; equivalente con `piano["tradotto"]`; riga `tradotto` nel diario PRIMA della riga `ordine`; `_emetti` riporta ogni evento nei termini del CHIESTO (`_riporta_tradotto`, r. 621, con la riga vera in `riga_mandata`); rifiuto `M_SOTTO_MINIMO` (r. 111); sorveglianza `INVALID_BET_SIZE` dei place LIVE (`_sorveglia`, `_emetti_specchio` r. 1751 che trattiene la riga terminale, `avanza_sorvegliati` r. 1778, `_ripiega` r. 1864): UN ripiego ai 0,50 con `ripiego_050` dichiarato, poi mai piu'; la taglia rifiutata `(mode, lato, size)` non si ritenta identica |
| `stream/live_order_worker.py` | `_place_closing_leg` (r. 2101): in LIVE sotto il minimo va DIRETTO al place-and-trim, deciso prima dell'invio (prima: place diretto, e il ripiego solo dopo un rifiuto dei control); opt-out `allow_sub_minimum=False` -> rifiuto esplicito; `_costruisci_chiusura` (2167) per greenup e cash-out; `verifica_importo_finale` in `_place_sub_minimum` (1343) e `_start_submin` (2982). Niente equivalente nel greenup: il follow-through rilegge la STESSA selezione e rifarebbe l'hedge |
| `stream/trading/submin.py` | `verifica_importo_finale` (317, regola d'ingresso: finale >= 0,50); `quota_parcheggio_lontano` (337): parcheggio LAY a `1 + 0,008/size` al tick superiore, contro `INVALID_PROFIT_RATIO`; rifiuto `SUBMIN_PARCHEGGIO_ABBINABILE` se il parcheggio lontano si abbinerebbe subito; `SUBMIN_ABS_MIN_SIZE` importato da build. Nessuna guardia in `advance_submin` (opzione B) |
| `safe_strategy/execution.py` | `_min_size_live` (71) da `minimi_it`; `sotto_minimo_chiusura` / `submin_fuori_canale` (782): sulla CODA e sul REST anche una chiusura sotto il minimo va al place-and-trim; sul CANALE decide il motore. Sotto il minimo E sotto 0,50, fuori dal canale: rifiuto CERTO uguale in paper e in live (r. 823), nessuna riga in coda e nessun REST |
| `omega/omega_market.py` | `SUBMIN_MIN_BACK/LAY` da `minimi_it` (r. 830; prima 2,00/0,50 fissi, sfasati rispetto al nucleo); `verifica_importo_finale` -> `PlaceRifiutato(error_code=SOTTO_MINIMO_NON_PIAZZABILE)` (r. 1007) |
| `stream/config_stream.py` | solo commento |
| test aggiornati (vecchie regole) | `test_live_order_build`, `test_submin`, `test_submin_nucleo`, `test_submin_contratto_chiamanti`, `test_motore_ordini_2026_09_24`, `test_live_order_worker`, `test_cashout_pro`, Safe `test_audit`/`test_cert`/`test_execution`/`test_p_blocco3`/`test_safe_kill_switch_rest_o1`, Omega `test_place_and_trim`/`test_ref_strategia`. Nei test di LOGICA delle uscite con importi minuscoli (Safe `test_bot_service` x3, `test_audit` x1, Omega `test_omega_audit` x3, `test_omega_greenup` x2) ho isolato la logica dai minimi con la manopola esistente `SAFE_MIN_SIZE_LIVE=0.01` (commento in ogni test) |
| `stream/tests/test_runner_minimi_chiusure_2026_10_01.py` (nuovo) | 21 test, par. 5 |

NB: tutti i test della tabella sopra sono poi stati riallineati ai minimi definitivi (par. 6).

## 4. Ordine chiesto -> verdetto -> ordine mandato

| ordine chiesto | mercato | verdetto | ordine mandato |
|---|---|---|---|
| banca Over 0,43 @18 (chiusura di Mike, oggi) | 2 esiti | equivalente | punta Under **7,31 @1,06**; il bot vede banca Over 0,43 @18 abbinata 0,43 @18,0. Scarti: +0,0000 se vince Over, +0,0086 se vince Under (1,05 avrebbe peggiorato il limite) |
| punta Under 7,47 @1,03 | qualunque | diretto | 7,47 al centesimo (prima 7,00) |
| banca 0,30 @18 | 2 esiti | equivalente | punta 5,10 @1,06 |
| banca 0,30 @18 | 3+ esiti | impossibile | nessuno: `SOTTO_MINIMO_NON_PIAZZABILE`, residuo dichiarato |
| banca 0,60 @18 | 3+ esiti | submin | parcheggio 1,00 a 1 + 0,008/0,60 = 1,02, taglio a 0,60, riprezzo a 18 |
| punta 0,70 @3 | 3+ esiti | submin | parcheggio 1,00 @1000, taglio a 0,70, riprezzo |
| punta 0,49 | qualunque senza equivalente | impossibile | nessuno |
| banca 0,30 @12 | 2 esiti | equivalente | punta 3,30 @**1,10** (il tick piu' vicino 1,09 sarebbe un limite peggiore) |
| punta 0,80 @1,30 | 2 esiti | submin (l'equivalente, banca 0,24, e' sotto il minimo) | place-and-trim |
| punta 7,47 rifiutata `INVALID_BET_SIZE` (live) | - | ripiego unico | 7,00, `ripiego_050: residuo 0,47`; un secondo rifiuto viene emesso come «rifiutato», senza terzi tentativi |
| ancora 7,47 dopo quel rifiuto | - | rifiuto | `SOTTO_MINIMO_NON_PIAZZABILE: ... non si ritenta identico` |

## 5. Test e falsificazione

- **Test nuovi**: `test_runner_minimi_chiusure_2026_10_01.py`, **21 passed**. Coprono:
  - le regole pure;
  - l'equivalenza ±0,01 sui numeri di oggi;
  - il tick mai peggiore;
  - il riporto degli abbinati;
  - il parcheggio contro `INVALID_PROFIT_RATIO`;
  - le chiusure live del worker (nessun place diretto; opt-out);
  - il motore VERO (fixture `amb`: LocalChannel, client e strategie, ordini flumine veri):
    traduzione, diario, eventi riportati, rifiuto senza REST, place-and-trim, idempotenza
    sull'aggancio, ripiego 0,50 solo dopo un `INVALID_BET_SIZE` reale e una sola volta,
    nessun ripiego per altri codici, taglia non ritentata.

  La risposta di Betfair e' simulata come in `BetfairExecution.execute_place`
  (`responses.placed(report FAILURE)` + `execution_complete()`).
- **Falsificazione**: `falsifica_runner_minimi.py`, output in `falsifica_runner_minimi_out.txt`.
  Le 8 mutazioni sono tutte **ROSSE** e i file vengono ripristinati (21 passed dopo):
  - M1: esenzione `reduces_liability` rimessa;
  - M2: floor della punta a 0,50;
  - M3: tick dell'equivalente al piu' vicino;
  - M4: eventi non riportati;
  - M5: niente ripiego;
  - M6: taglia ritentata;
  - M7: floor 0,50 del trim tolto dal verdetto;
  - M8: regola d'ingresso della macchina tolta.

  Al primo giro M3 e M7 erano VERDI: ho aggiunto il caso 0,30 @12 e corretto la mutazione M7.
- **Suite ufficiale piu' tennis e Mike** (`Betfair/stream/tests Betfair/safe_strategy
  Betfair/omega Betfair/stream/tennis_live/tests Betfair/stream/tennis_scalper/tests
  Betfair/mike`):
  - prima del lavoro: 6728 passed nella suite ufficiale e 2337 passed fra tennis e Mike;
  - **finale: 9089 passed, 0 failed, 31 skipped, 9 xfailed.**
- **`Betfair/` intera**: 9221 passed, 9 xfailed, 1 failed. Il rosso c'e' gia' su master
  (par. 0).

## 6. Il riallineamento dei 121 test (fatto il 01/10 sera)

**Regola seguita** (tua): cambio SOLO i numeri e le attese dei test che descrivono il
listino, con la riga di motivo «minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim
>= 0,50». Il comportamento dei bot non cambia per far passare un test. Le condotte diventate
impossibili per legge vanno in xfail (reperto 1).

**Schema dei cambi:**
- l'importo «sotto il minimo» usato per esercitare il place-and-trim passa da 1,20 / 1,35 /
  1,50 a **0,70 / 0,72 / 0,75 / 0,76**;
- il parcheggio passa da 2,00 a **1,00**;
- le riduzioni attese vengono ricalcolate (per esempio 2,00 - 1,35 = 0,65 diventa
  1,00 - 0,75 = 0,25);
- «porta al minimo» del tennis da 2,00 / 0,50 a **1,00 / 1,00**;
- la punta e' legale al centesimo: le attese 2,0 / 3,5 diventano 2,3 / 3,7;
- banca minima 1,00: 0,93 diventa 1,93;
- i rifiuti per importo vanno a **0,99** (sotto il diretto) o a **0,49** (sotto il trim).

File toccati, con il numero di test riallineati:

| file | test |
|---|---|
| `stream/tests/test_live_order_build.py` | 3 |
| `test_submin.py` | 3 |
| `test_submin_contratto_chiamanti_2026_09_17.py` | 2 |
| `test_submin_nucleo_2026_09_17.py` | 6 |
| `test_audit_fixes_2026_07.py` (dutch: stake 4,00 su 6 gambe, cioe' circa 0,67 a gamba) | 1 |
| `test_live_order_worker.py` | 5 |
| `test_cashout_pro_2026_09_10.py` | 6 |
| `test_motore_ordini_2026_09_24.py` | 8 |
| `test_motore_ritiro_pendente_d1ter_2026_09_28.py` | 5 |
| `test_motore_submin_fok_caso_b_d1ter_2026_09_28.py` | 5 |
| `test_porta_banco_f4_2026_09_24.py` | 1 |
| `test_strada_unica_banco_2026_09_25.py` | 2, piu' lo scenario R8 del banco (sotto) |
| Safe `test_audit_2026_09_11.py` | 3 |
| Safe `test_cert_2026_09_13.py` | 1 |
| Safe `test_execution.py` | 4 |
| Safe `test_p_blocco3_2026_09_28.py` | 6 (due rinominati: `..._072_diventa_100`, `..._sotto_050_diventa_100`) |
| Omega `test_place_and_trim_2026_09_13.py` | 15 |
| Omega `tests/test_ref_strategia_per_attore_r1_2026_09_24.py` | 1 |
| tennis `test_cantiere_d2_minimo_e_specchio_2026_09_28.py` | 10 |
| tennis `test_motore_ordini_tennis_2026_09_25.py` | 1 |
| tennis `test_tennis_order_payload.py` | 2 |
| tennis `test_tennis_cashout_amount_2026_09_10.py` (hedge 0,80 sotto la banca minima: amount 1,20) | 1 |
| tennis `test_cantiere_d2_chiusure_esatte_2026_09_28.py` | 4 riallineati, 5 xfail |
| tennis `test_cantiere_d2_chiusure_via_bot_2026_09_28.py` | 3 xfail |
| `tennis_scalper/tests/test_condotta_ordini_2026_09_17.py` | 12 |
| Mike `tests/test_mike_d1ter_submin_fok_parita_2026_09_28.py` (usa `safe_strategy.execution`; il motore di Mike non e' toccato) | 2 |
| `Betfair/tests/test_consapevolezza_ordine_2026_09_16.py` (fuori dalla suite ufficiale, trovato col giro intero) | 1 |

**Profili rapidi e scenario R8.** Lo scenario R8 sta nel codice del banco,
`stream/backtest/trasporto_rapido.py`, in `_r8` e `_r8_tennis`. Prima mandava una punta da
1,50 come «sotto il minimo»; ora manda 0,70 (calcio: place-and-trim con parcheggio 1,00;
tennis: portata al minimo 1,00), con la riga di motivo. Anche il testo N/A di Omega e' allineato
(«stake 1,00 pari al minimo .it 1,00»). Sono cambiati solo i numeri del listino: i controlli
sono gli stessi. Esito: `test_strada_unica_banco[safe_base]` e
`test_profilo_rapido_safe_tennis_sulla_registrazione_vera` VERDI.

## 7. Replay (banco comune, registrazione 35760084, `--data-dir ..\_live_raw`)

Durata dichiarata prima del lancio: sotto i 10 minuti ciascuno.

| replay | durata | esito | confronto |
|---|---|---|---|
I replay sono stati rilanciati DOPO il riallineamento:

| replay | durata | esito | confronto |
|---|---|---|---|
| `omega 35760084 --scenari base` | 41 s | OK, decisioni 438, azioni 0 | **identico** a `omega_base_BOT_MAI_CIECHI.txt` riga per riga; sola differenza una riga `CRITICAL:omega.service` del logger (cattura di stderr, non del referto) |
| `safe_base 35760084 --trasporto entrambi` | 65 s | OK coda e canale, PARITA' RAGGIUNTA, 0 ordini | non esiste un referto precedente con lo stesso comando; nello scenario base Safe non piazza, quindi i minimi qui non sono sollecitati |
| `safe_base 35760084 --scenari ordini-manuali --trasporto coda` | 51 s | OK | **identico** (0 righe diverse su 211) a `safe_base_ordini_manuali_coda_BOT_MAI_CIECHI.txt` |
| profilo rapido `safe_base` (R1-R9) e profilo rapido `safe_tennis` | dentro la suite | VERDI | R8 riallineato ai minimi definitivi (par. 6) |

Mike non l'ho rilanciato: il suo motore non e' toccato e il suo trasporto e' il canale, che
qui e' coperto dai test del motore.

## 8. Reperti aperti (opzione B: fuori perimetro, da decidere con l'utente)

1. **Bot che costruiscono il place-and-trim da se'.** Sono `stream/scalper/scalper_bot.py`
   (r. 2636), `scalper/sniper_bot.py` (1092), `tennis_scalper/tennis_scalper_bot.py` (2651) e
   le uscite esatte del tennis (`tennis_scalper/condotta_ordini.UsciteEsatte`, che usa
   pro/flb/swing). Creano lo `SubminState` e chiamano `advance_submin` senza passare dagli
   ingressi del motore, quindi NON hanno la regola «finale >= 0,50».
   - Le chiusure «esatte al centesimo» del 28/09 riducono un parcheggio fino a QUALUNQUE
     residuo (0,30, 0,05...). **Su .it sotto 0,50 sono IMPOSSIBILI PER LEGGE** (DM 47/2013
     art. 8) e sotto 1,00 non sono ordini diretti.
   - Inoltre `condotta_ordini.diretta_ok` e `spezza_esatta` impongono ancora il passo 0,50
     sulla punta. Li importano dai minimi condivisi, che ora valgono 1,00: dal tennis
     arriveranno quindi parcheggi da 1,00.
   - Proposta: lo stesso verdetto del motore. Prima l'equivalente sulla stessa selezione
     (Match Odds tennis = 2 esiti, quindi quasi sempre possibile), poi il trim solo con
     finale >= 0,50, sotto il residuo dichiarato. La guardia andrebbe nel nucleo
     (`advance_submin`, solo .it), cosi' vale per tutti.
   - Stima: mezza giornata di codice, piu' i test di quei bot. Con la guardia nel nucleo e i
     minimi intermedi erano 179 rossi: va rimisurato coi minimi definitivi.
   - **Test in xfail del reperto 1** (motivo `XFAIL_REPERTO_1` nel file; elenco in
     `RUNNER_MINIMI_CHIUSURE_xfail.txt`). Descrivono chiusure «esatte» di pro/flb/swing col
     resto ridotto sotto 0,50, cioe' IMPOSSIBILI per legge su .it:
     - `test_cantiere_d2_chiusure_esatte::test_copertura_esatta_al_centesimo_nel_runner_paper`
       (flb, pro, swing): resto 0,15;
     - `::test_copertura_tutta_sotto_il_minimo_esatta`: punta 1,05 col passo 0,50, quindi
       1,00 diretti piu' 0,05 di resto;
     - `::test_spezza_esatta_la_somma_e_sempre_la_size[1.98-BACK]`: 1,50 piu' 0,48 di resto;
     - `test_cantiere_d2_chiusure_via_bot::test_chiusura_esatta_guidata_dai_book_del_bot`
       (flb, pro, swing): resto 0,15.

     Fanno 8 xfail; il nono xfail della suite c'era gia'
     (`test_svuota_le_cache_d2::test_reperto_azzera_canale_scan...`).
   - Altri test di quei bot descrivono resti sotto 0,50 ma oggi PASSANO, perche' la funzione
     pura non e' cambiata. Restano verdi e vanno ripresi col reperto: per esempio
     `spezza_esatta` 2,02 -> 2,00 + 0,02 e 3,15 -> 3,00 + 0,15, e le coperture 0,20 del FLB.
     Lo stesso vale per scalper, sniper e scalper tennis, che non sono stati sollecitati
     dai minimi nuovi.
2. **Mike** (`mike/engine.py`: `IT_BACK_MIN=2.0`, `IT_LAY_MIN=0.50`, `IT_BACK_STEP`,
   `SUBMIN_FLOOR`) ha costanti sue, che sono duplicati. Il delegato di Mike deve importare
   `Betfair.stream.trading.minimi_it` (`IT_MIN_BACK`, `IT_MIN_LAY`,
   `SUBMIN_IMPORTO_FINALE_MIN`, `IT_FLOOR_LEGGE`, `SOTTO_MINIMO_NON_PIAZZABILE`). Altri
   duplicati: nessuno nel runner. In `omega_market` restano `SUBMIN_PARK_PRICE_BACK/LAY`,
   costanti non usate dal piano.
3. **Omega e Safe, uscite a importi minuscoli: divergenza di STRATEGIA, segnalata a parte**
   in `RUNNER_MINIMI_REPERTO_3_DIVERGENZA_STRATEGIA.md`, da portare all'utente domani.
   - Il take-profit di Omega a 1000 vale circa 0,28 EUR e i residui di Safe stanno sotto 0,50:
     in live Betfair li rifiutava gia'.
   - Le strategie NON sono toccate. I 9 test di logica relativi isolano i minimi con la
     manopola `SAFE_MIN_SIZE_LIVE`.
4. **Arrotondamento al tick e cross-matching.** L'equivalente al tick «mai peggiore» (1,06)
   potrebbe non abbinarsi dove il libro dell'altra selezione mostra il prezzo virtuale
   arrotondato contro di noi (1,05). Con un FOK il bot vede «scaduto» e ripete secondo la sua
   logica. Va guardato dal vivo.
5. **Cancel parziale con `size_reduction` di un ordine tradotto.** Il bot ragiona nei suoi
   termini (es. 0,20 su 0,43) ma l'ordine vero e' 7,31: la riduzione non viene convertita.
   Oggi nessun bot riduce le chiusure.
6. **LiveExposureControl per selezione.** L'equivalente su una selezione senza posizione
   puo' sembrare un'apertura a quel controllo. Un eventuale rifiuto e' esplicito (False ->
   errore al bot).
7. **Gambe greenup/cash-out in PAPER.** Restano dirette sotto il minimo
   (`simulato_ammette_sotto_minimo`, comportamento di sempre). In live vanno al
   place-and-trim, che col finale >= 0,50 diventa un rifiuto se sotto 0,50.

## 9. Cosa NON e' verificato

- **NESSUN ordine vero e' stato mandato.** Restano da provare dal vivo, con un ordine piccolo
  deciso dall'utente:
  - che punta e banca da 1,00 passino;
  - che una punta non multipla di 0,50 passi sempre (oggi 7,47 si');
  - che il trim a 0,50 sia accettato;
  - che l'equivalente 7,31 @1,06 si abbini dove l'originale si sarebbe abbinato.
- Il ripiego 0,50 e la sorveglianza sono provati sul finto della risposta di flumine, non su
  un `INVALID_BET_SIZE` vero. E' ancora da vedere se lo specchio riceve davvero la riga
  terminale di un place fallito senza bet_id: oggi la sorveglianza legge l'ordine
  dall'oggetto in RAM e non ne dipende.
- La CRONOSTORIA non l'ho toccata.
- La junction `.venv` resta da togliere (la togli tu).
