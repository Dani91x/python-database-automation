# MIKE - chiusura della copertura-banca sotto il minimo (01/10/2026)

Delegato Opus, worktree `agent-a23e39cd37caead01` da master `ebfab2a`. Nessun commit.
Patch: `AUDIT_2026-10-01/MIKE_CHIUSURA_COPERTURA.patch` = `git diff ebfab2a` + i 3 file nuovi
(`Betfair/stream/trading/minimi_it.py`, `test_mike_chiusura_copertura_2026_10_01.py`,
`ResiduoScopertoMike.test.tsx`). Nel frattempo master e' andato a `a0dc4e7`, che NON tocca nessuno
dei 16 file della patch (solo Safe e AUDIT): `git diff master` avrebbe portato dentro il rovescio di
quei commit, quindi la patch e' contro la base. `minimi_it.py` alla fusione: tenere quello del runner.
Strumenti di verifica (non consegnati, nel worktree): `.scratch_mike/` (falsifica, differenziale,
confronto referti, traccia scenario, query REST in sola lettura).

## 1. Il fatto e la causa (verificati sul DB in sola lettura e sul codice)

FC Ashdod v Maccabi Herzliya (36134689), LIVE: punta Under 3,5 5,00 @ 1,54 + banca Under 4,5
6,32 @ 1,23. 19:07:01 «profit smart 0,13»: banca Under 3,5 6,21 @ 1,24 abbinata; banca Over 4,5
0,43 @ 18 rifiutata `INVALID_BET_SIZE`, 21 righe (`mike_trades` 5116-5136) in 24 s, poi
`FLAT «chiuso (profit)»` e subito `LIVE_COVERED «esposizione residua»`. Esposizione rimasta:
-1,45 se vince l'Under 4,5, +6,32 se vince l'Over.

Cause (tutte confermate):
1. `ripiego_chiusura_sotto_minimo` voleva la puntata Under «multipla di 0,50»: 7,55 non lo era,
   restava la banca 0,43.
2. `size_chiudibile` ragionava al centesimo («le chiusure riducono il rischio»): falso su .it.
   Prove: le uniche chiusure live di Mike sotto il minimo con esito sono quelle di oggi, tutte
   rifiutate; nessuna banca live fra 0,50 e 1,00 mai abbinata nel nostro storico (query REST in
   sola lettura su `mike_trades`/`safe_strategy_trades`/`omega_trades`); la riga 5096 (punta 0,09)
   e' un ordine dell'UTENTE (Cash Out del sito), non dell'API.
3. `_decide_closing` con `pend` vuoto ritentava a ogni giro (il ritmo guardava solo i pending).
4. a tentativi esauriti `FLAT «chiuso (close_reason)»` con esposizione viva, nessun avviso.

Reperti nuovi trovati lavorando (fuori dal brief, money-critical):
* **R1 - il banco accetta ordini sotto il minimo**: il motore simulato abbina banche da 0,01-0,59
  (sintetiche `_synth_mike_reingresso`: green del rientro 0,59 / 0,14 / 0,03 / 0,01 tutte
  «abbinate»). Per questo il difetto non era mai emerso nel replay. Da correggere nel banco
  (dominio del runner/banco): il simulatore deve rifiutare come Betfair.
* **R2 - uscita in perdita senza firma** (introdotto e poi CORRETTO in questo lavoro, trovato dal
  replay `copertura-rifiutata-legacy`): togliendo gli ordini sotto minimo da una decisione di
  uscita in perdita, `gate_uscite` non vedeva piu' la categoria e lasciava passare lo stato
  LIVE_CLOSING senza firma; al giro dopo l'ordine (diventato piazzabile) partiva. Corretto in
  `gate_uscite` (categoria «chiusura» da stato+motivo), test + mutazione M15.

## 2. Modifiche (file:riga del worktree)

`Betfair/stream/trading/minimi_it.py` (NUOVO, nomi e valori dati dal coordinatore, uguali alla
patch del runner): `IT_MIN_BACK=1.00`, `IT_MIN_LAY=1.00`, `IT_FLOOR_LEGGE=0.50`,
`SUBMIN_IMPORTO_FINALE_MIN=0.50`. Alla fusione vale la versione del runner: Mike la IMPORTA.

`Betfair/mike/engine.py`
* r.27-31, 73-87: costanti duplicate tolte (`IT_BACK_MIN 2.0`, `IT_BACK_STEP 0.5`, `IT_LAY_MIN
  0.50`) -> import da `minimi_it`; `IT_BACK_STEP = 0.01` (nessun passo); `SUBMIN_FLOOR` resta solo
  come «esiste un ordine al centesimo» (non e' un minimo di piazzamento).
* `via_ordine` / `minimo_listino` (~r.700-745): GUARDIA UNICA del minimo, per ruolo e lato
  (tabella al par. 3).
* `puntata_equivalente` + `ripiego_chiusura_sotto_minimo` (~r.975-1030): banca di chiusura sotto
  1,00 -> PUNTA equivalente sull'altra selezione al centesimo, in ENTRAMBE le forme della copertura;
  tolto il vincolo del multiplo di 0,50.
* `cashout_value` (~r.1075): con il ripiego il valore bloccato e' quello della puntata che parte.
* `chiusura_gia_rifiutata`, `RIFIUTI_PER_TAGLIA` (INVALID_BET_SIZE, SOTTO_MINIMO_NON_PIAZZABILE),
  `attesa_ritento_chiusura` (~r.1925-1965).
* `size_chiudibile(size, side)` (~r.2140): per lato = guardia; senza lato = centesimo (solo per
  `residuo_non_chiudibile`).
* `_close_actions` (~r.2200): ripiego prima, poi guardia; niente annullo se la chiusura non parte.
* `_decide_flatten` (~r.2615): «Chiudi» con ordine sotto minimo -> lo dice + proposta.
* blocco nuovo prima di `decide` (~r.2700-2930): `_ordini_che_chiudono`, `_proposta_residuo`
  (episodio: un solo avviso CRITICAL per ciclo), `_alternative_residuo`, `_guardia_minimo_listino`,
  `_controllo_di_piatto`, `_dichiara_residuo`, `_proposta_residuo_finale`, `_ultime_guardie`;
  `decide` le applica dopo `gate_uscite` e sul ramo del flatten.
* `_decadi` (r.~3125): la proposta del residuo non decade nel cancello.
* `gate_uscite` (r.~3175): reperto R2.
* `_decide_closing` (r.~4700): ritenti col ritmo `close_retry_s`, mai lo strumento rifiutato per
  taglia, «chiuso» solo se piatto (altrimenti lo smentisce `_controllo_di_piatto`); riprezzo che
  non scende sotto il minimo.
* testi della copertura «sotto il minimo di %.2f» (non piu' 0,50 scritto a mano); tranche minima
  col place-and-trim = `SUBMIN_IMPORTO_FINALE_MIN`.

`Betfair/mike/service.py`: `_registra_avvisi_esecuzione` (r.~4574, chiamata a r.~5276):
`chiusura_parziale` e `ordine_sotto_minimo` in `mike_activity` + `logger.critical`;
`_request_approva_uscita`: la proposta del residuo non si approva (`proposta_non_approvabile`,
in `_REJECT_CODES`).

`Betfair/mike/certificazione.py`: G3 esclude la proposta del residuo; controlli nuovi **L1**
(nessuna chiusura sotto il minimo, nessuna banca sotto 1,00) e **L2** (mai FLAT con esposizione
chiudibile), con i minimi di `minimi_it` (non con la guardia del motore). Controlli attivi 47 -> 49.

UI (testi minimi, nessun componente nuovo): `frontend/src/lib/mike.ts` (kind `chiusura_parziale`,
`ordine_sotto_minimo`, codice `proposta_non_approvabile`), `PropostaUscitaMike.tsx` (categoria
`residuo_scoperto`: titolo «Mike NON riesce a chiudere da solo», niente «approva», scelte
dell'utente), `mikeEsitoChiusura.ts` (NON COMPLETA con il residuo, motivo senza «profitto»).

## 3. Tabella C - ordini di Mike, minimo, via sotto minimo

| ordine (ruolo) | lato | minimo diretto | sotto il minimo |
|---|---|---|---|
| under_entry, under_last, under_second, reentry | punta | 1,00 | place-and-trim (`execution.place`) se >= 0,50; legalizzata a 1,00 con `exact_sizes` spento; sotto 0,50 non si manda |
| over_cover forma di prima (punta Over 4,5) | punta | 1,00 | come sopra; tranche sotto 0,50 -> copertura in una volta |
| over_cover di serie (banca Under 4,5) | banca | 1,00 | non si manda (resto sotto 1,00 = «coperta», M3.5); la guardia toglie ogni banca < 1,00 |
| under_green, ko_green, reentry_green | banca | 1,00 | non si manda: CRITICAL `ordine_sotto_minimo` + proposta |
| under_close (Under 3,5) | banca | 1,00 | nessuno strumento equivalente (l'Over 3,5 non e' nel feed): residuo dichiarato |
| over_close (4,5, entrambe le forme) | banca | 1,00 | **punta equivalente** sull'altra selezione se >= 1,00; altrimenti residuo dichiarato |
| over_close come punta Under (ripiego) | punta | 1,00 | residuo dichiarato |
| manual_close («Chiudi», cash out) | per lato | 1,00 | equivalente sul 4,5; altrimenti «sotto il minimo» + proposta |

Le chiusure non passano mai dal place-and-trim (vincolo 4 del coordinatore e
`execution.place`: `sotto_minimo` solo per chi non chiude).

## 4. Come ho recepito i messaggi del coordinatore

* A guardia unica: `via_ordine` + `_guardia_minimo_listino` su ogni decisione (anche flatten).
* B controllo di piatto: `_controllo_di_piatto`; il caso Ashdod finisce in «chiusura parziale»
  con proposta «punta Under 4,5 7,55 @ 1,03»; mutazione M4 -> 8 rossi.
* C: tabella al par. 3.
* Ricerca 1: passo 0,50 tolto (`IT_BACK_STEP = 0.01`), centesimo; esenzione `reduces_liability`
  in `live_order_build.min_stake_rules` (r.18-19, 147-150) e `is_closing` in `execution.place`
  (r.~735) sono FALSE su .it: Mike non ci conta piu' (la guardia ferma tutto prima). NON le ho
  tolte: sono codice condiviso (Safe/Omega/tennis/runner), il classificatore mi ha negato la
  modifica di `live_order_build.py`; restano al delegato del runner.
* Ricerca 2 / vincoli definitivi 1-2: punta equivalente preferita quando la banca e' sotto 1,00,
  in entrambe le forme; banca minima 1,00 MAI diretta sotto. NON applicato «di serie a ogni
  importo»: con banca >= 1,00 la chiusura resta la banca Over (decisione dell'UTENTE del 29/09,
  M3.3); cambiarla e' una decisione da chiedere all'utente (punto aperto 1).
* Vincolo 3: residuo dichiarato + CRITICAL + proposta con le due scelte («lasciare il residuo»,
  «aumentare la posizione di un importo minimo e poi chiudere tutto»).
* Vincolo 4 / ricerca 3: nessun place-and-trim per le chiusure; per le aperture importo finale
  >= 0,50 (`SUBMIN_IMPORTO_FINALE_MIN`). Parcheggio e banda INVALID_PROFIT_RATIO: non toccati
  (sono in `omega_market`/runner).
* Ricerca 4: sbilancio di pochi centesimi accettato e DICHIARATO (proposta), mai un ordine
  impossibile.
* Correzione definitiva (punta 1,00 / banca 1,00, modulo `minimi_it`): fatto, test resi
  indipendenti dal valore dove possibile.
* `SOTTO_MINIMO_NON_PIAZZABILE` del runner: trattato come INVALID_BET_SIZE (strumento bloccato,
  niente ritenti, residuo dichiarato). Limite: arriva a Mike solo se il codice e' nel motivo del
  rifiuto (via sincrona `execute_place`); l'evento asincrono del runner (`CHIAVI_SPECCHIO`) non
  porta codici: va aggiunto dal delegato del runner se vuole che Mike lo legga anche li'.

## 5. Test

Suite: prima 1416 passed (`Betfair/mike`); dopo **1560 passed** (`Betfair/mike` +
`Betfair/stream/backtest`, 2 warning di sempre). `Betfair/stream/tests`: 3213 passed, 25 skipped.
Frontend: `tsc` 0 errori; vitest mirato 92/92 (4 file); vitest completo (prima delle ultime due
modifiche a `PropostaUscitaMike`) 315 file / 4834 passed.

Test nuovi: `Betfair/mike/tests/test_mike_chiusura_copertura_2026_10_01.py` (numeri veri di
Ashdod) e `frontend/src/components/controlroom/ResiduoScopertoMike.test.tsx`. Conti:
* (a) chiusura del 4,5 = punta Under 4,5 **7,55 @ 1,03** (6,32 x 1,23 / 1,03 = 7,5472); i 7,47
  dell'utente sono il green-up a 1,04 (7,7736 / 1,04 = 7,4746). Coi prezzi delle 19:07 (Over a 18)
  il piano della banca e' esattamente 0,43 @ 18 (fedelta'), il ripiego e' 7,33 @ 1,06.
* (b) chiuse tutte: P&L piatto su ogni totale = `cashout_value.net` = **+0,33** (prima il valore
  contava la banca impossibile: -1,38 invece di -1,23 sul 4,5).
* (c) `execute_place` VERO con `PlaceResult` vero `INVALID_BET_SIZE` -> 1 sola chiamata, nessun
  ritento dello strumento a nessun importo, LIVE_CLOSING «chiusura parziale», CRITICAL in log e
  in `mike_activity`, proposta non approvabile.
* (d) orologio finto: niente ordini a +1/+3/+9,9 s, ordine a +10 s; 24 giri al secondo -> al piu'
  1 ordine ogni 10 s, mai lo stesso; FOK non abbinato ritentato uguale dopo 10 s, senza avviso.
* (e) non regressione: forma di prima e banca >= 1,00 con i numeri del motore di master
  (calcolati con `ebfab2a`: banca Over 1,81 @ 4,3 e 1,63 @ 4,3, cash out 0,27 e 1,15).
* differenziale motore master vs corretto (432 casi con libri coerenti): 180 identici, 252 diversi
  tutti spiegati (124 master manda una chiusura sotto minimo, 128 master banca dove ora c'e' la
  punta equivalente); 0 non spiegati (`.scratch_mike/differenziale.py`, non consegnato).

Test esistenti cambiati (premessa smentita dal fatto di oggi o dai minimi 1,00), uno per uno nel
diff con il motivo nel docstring: `test_mike_audit_2026_09_12` (2), `test_mike_audit_2026_09_11`
(kind dichiarati), `test_mike_p5_copertura_banca` (4), `test_mike_p5_4b` (2),
`test_mike_p5_compensazione_mercato` (2), `test_mike_engine` (2: legalizzazione senza passo),
`test_mike_flusso_fischio_2026_09_13` (2: trim finale >= 0,50, minimo punta 1,00).

## 6. Falsificazione (`.scratch_mike/falsifica.py`, ripristino da copia + impronta)

| mutazione (comportamento vecchio rimesso) | rossi |
|---|---|
| M1 vincolo del multiplo di 0,50 nel ripiego | 11 |
| M2 guardia/size_chiudibile permissive (chiusura sotto minimo parte) | 55 |
| M3a ritento a ogni giro (close_retry_s ignorato) | 2 |
| M3b rifiuto per taglia ignorato | 4 |
| M4 controllo di piatto tolto (FLAT «chiuso (profit)» con residuo) | 8 |
| M5 guardia finale tolta | 11 |
| M6 cash out con la banca impossibile | 1 |
| M7 proposta del residuo che decade nel cancello | 1 |
| M8 annullo anche se la chiusura non parte | 4 |
| M9 banca minima 0,50 | 31 |
| M9b ripiego solo con la copertura-banca | 2 |
| M10 «Chiudi» sotto minimo senza proposta | 1 |
| M11 FOK mancato = rifiuto definitivo | 1 |
| M12 banca d'apertura sotto 1,00 ammessa | 15 |
| M13 proposta senza le scelte dell'utente | 1 |
| M14 un CRITICAL a ogni cambio dell'ordine | 1 |
| M15 uscita in perdita senza firma (R2) | 1 |
| M16 punta minima 2,00 duplicata | 4 |
| M17 passo da 0,50 | 3 |
| M18 trim sotto 0,50 | 5 |
| M19 SOTTO_MINIMO_NON_PIAZZABILE ignorato | 1 |

Tutte rosse, `engine.py` ripristinato (impronta identica). Output completo: `MIKE_CHIUSURA_COPERTURA_falsifica.out`.

## 7. Replay del banco

Comandi (`--data-dir` = `_live_raw` del checkout principale, in sola lettura), lanciati uno alla
volta, con lo script `.scratch_mike/replay_tutti.ps1`:
`certifica mike <5 sintetiche> --scenari base --trasporto canale`;
`certifica mike 35760084 --scenari tutti --trasporto canale`;
`certifica mike 35760084 --scenari copertura-rifiutata,copertura-rifiutata-legacy --trasporto entrambi`.
Riferimento = gli stessi tre comandi sul codice di MASTER `ebfab2a` (esportato con `git archive`
in `.scratch_mike/master`, non sul referto del 30/09: master ha scenari e cambi successivi).

| referto | master ebfab2a | corretto | durata (TEMPO TOTALE del banco) |
|---|---|---|---|
| sintetiche (5) | 5 OK, 0 violazioni | 5 OK, 0 violazioni | 26,6 s -> 16,0 s |
| tutti (26 scenari) | 26 OK, 0 violazioni | 26 OK, 0 violazioni | 533,6 s -> **719,8 s** (stessa decisione, run precedente identico nei numeri: 489,3 s) |
| coperture (4) | 4 OK, 0 violazioni | 4 OK, 0 violazioni | 100,9 s -> 159,2 s |

Durata: l'ultimo `tutti` ha passato il tetto (720 s > 600) con la macchina carica (altri processi
python di altre sessioni); lo stesso codice, a parita' di decisioni e numeri, aveva fatto 489 s, e
master 534 s. Il banco era gia' sopra l'obiettivo di 300 s su master: difetto di velocita' del banco
da misurare col profilo (§6.9), non introdotto qui.

Controlli attivi 47 -> 49 (L1, L2): sollecitati L1 x16/x99/x16, L2 x536/x9274/x4642, mai violati.
Confronto riga per riga: `replay/CONFRONTO_MASTER_vs_CHIUSURA_COPERTURA.txt`. Scenari IDENTICI a
master: base, bot-fermo, cap-stretto, cashout-dopo-copertura, cashout-globale, chiuso-fuori-app,
copertura-legacy, copertura-rifiutata (canale e coda), esiti-ignoti, feed-stantio, fermo-copertura,
lettura-dati-ko, punteggio-ko, riavvio, rifiuti-betfair, senza-seconda-puntata, taker,
taker-esiti-ignoti. Quelli che cambiano, uno per uno (tracce con `.scratch_mike/traccia_scenario.py`):

* `chiusura-abbinata-in-parte`, `ko-green-parziale`: decisioni, ordini, fill e P&L identici; solo
  `uscita_proposta` 12 -> 18 righe: la proposta d'uscita in perdita non elenca piu' gli ordini sotto
  minimo, quindi cambia (e si riscrive) quando un ordine passa sopra/sotto il minimo.
* `copertura-rifiutata-legacy` (canale e coda): decisioni, fill e P&L identici; +1 riga
  `uscita_proposta` (l'uscita in perdita con l'unico ordine sotto minimo e' proposta senza ordini,
  poi con l'ordine quando diventa piazzabile: correzione R2). Senza R2 qui partiva una chiusura in
  perdita non firmata (fase 2 del lavoro, P&L -2,00 invece di -3,00): reperto chiuso.
* `firma-dopo-gol-decisivo` (+ `-senza-chiusura`): la chiusura del 4,5 e' abbinata in parte (3,00);
  il residuo 9,54 parte dopo `close_retry_s` (10 s) invece che al giro dopo: 1,34 invece di 1,35;
  P&L -2,14 -> -2,05.
* `uscite-automatiche`, `uscite-in-perdita-firmate`: master mandava banche di chiusura da 0,04 /
  0,12 / 0,13 (Betfair le rifiuterebbe) e il banco le «abbinava» (R1); ora non partono e la partita
  resta LIVE_CLOSING con «chiusura parziale» dichiarata (1 avviso), P&L -2,29 -> -2,45 e
  -2,23 -> -2,35 (i 16 / 12 centesimi sono il residuo che Betfair non avrebbe accettato).
* sintetiche: `_synth_mike_reingresso(_2gol)` master mandava le green del rientro 0,59 / 0,14 / 0,03
  / 0,01 (sotto minimo); ora si ferma a 2,43, dichiara il resto, P&L +3,28 -> +3,43.
  `_synth_mike_ultimo_ingresso(_riprova)`: banca al fischio 0,06 non mandata, il resto va in
  copertura, +0,31 -> +0,34. `_synth_mike_prezzo_migliore`: banca al fischio 0,27 e chiusura 0,28
  sotto minimo non mandate, la partita resta LIVE_CLOSING e non rientra: +3,55 -> +0,51 (punto
  aperto 3).

Referti: `replay/mike_{sintetiche,tutti,coperture}_CHIUSURA_COPERTURA.txt` (finali),
`..._MASTER_ebfab2a.txt` (riferimento), `..._fase1/2.txt` (versioni intermedie, prima dei vincoli
definitivi: non sono il referto finale).

## 8. Punti aperti per il coordinatore / l'utente

1. **Punta equivalente «di serie» anche con banca >= 1,00** (vincolo definitivo 1): NON applicata,
   contrasta con la decisione dell'utente M3.3 (29/09). Se l'utente la vuole e' una riga
   (`ripiego_chiusura_sotto_minimo`: togliere il controllo `size_chiudibile(plan.size, "lay")`);
   cambia le chiusure del 4,5 in `cashout-dopo-copertura`, `firma-*`, `uscite-*`.
2. **Il cash out ora vale la puntata che parte** (`cashout_value`): dove scatta il ripiego cambia
   il numero su cui decidono «profit»/«smart»/uscita a modello (non le soglie). Con libri coerenti
   la differenza e' piccola; con libri incoerenti (sintetici) puo' anticipare/ritardare una chiusura.
3. **Residuo non chiudibile = LIVE_CLOSING fino al regolamento**: in quello stato la strategia non
   rivaluta piu' le regole di LIVE_COVERED e non RIENTRA. Nel sintetico `_synth_mike_prezzo_migliore`
   un residuo Under 3,5 di 0,28 di banca ferma il rientro: +3,55 -> +0,51 (il +3,55 del master era
   fatto con banche sotto minimo che Betfair avrebbe rifiutato).
4. **Banco (R1)**: il simulatore accetta ordini sotto il minimo; finche' non li rifiuta come Betfair
   i P&L dei replay con residui piccoli sono ottimisti.
5. **Codice condiviso** (non toccato, negato dal classificatore / fuori perimetro):
   `live_order_build` (IT_BACK_MIN_STAKE 2,00, IT_BACK_STEP 0,50, IT_LAY_MIN_SIZE 0,50,
   esenzione `reduces_liability`), `safe_strategy.execution._min_size_live` (0,50/2,00 scritti a
   mano, esenzione `is_closing`), `omega_market.SUBMIN_MIN_*`: vanno portati su `minimi_it` dal
   delegato del runner. Mike non dipende piu' da quei valori per decidere.
6. Aperture: con `execution._min_size_live` ancora a 2,00, una punta d'apertura fra 1,00 e 2,00 va
   nel place-and-trim invece che diretta: funziona, ma e' piu' lenta (bet delay doppio). Si
   risolve quando `execution` legge `minimi_it`.

## 9. Cosa NON ho potuto verificare

* Nessuna prova dal vivo: che Betfair .it accetti la punta da 1,00 e la banca da 1,00 dirette via
  API viene dalla Nota informativa e dalla puntata dell'utente da 7,47 (sito), non da un ordine API.
* L'evento asincrono del runner con `SOTTO_MINIMO_NON_PIAZZABILE` (protocollo del runner, non nel
  mio albero).
* UI a schermo: solo test (vitest/tsc), nessun `npm run build` ne' controllo visivo nell'app.
* Uno scenario di banco nuovo «chiusura della copertura con banca sotto il minimo» non l'ho
  aggiunto: sulla registrazione 35760084 il cash out dopo la copertura avviene con l'Over a 4,3
  (banca 2,27: sopra il minimo). Specifica proposta: scenario `cashout-copertura-sotto-minimo` =
  `cashout-dopo-copertura` con `stake` 1,00 e richiesta di cash out mandata quando la banca Over
  di chiusura calcolata con `engine.cashout_value` e' sotto `IT_MIN_LAY`; controlli L1/L2 + atteso
  «punta equivalente» o «chiusura parziale» con proposta. I casi reali sotto minimo il banco li
  esercita gia' (L1 x16-99, L2 x536-9274 nei referti).
