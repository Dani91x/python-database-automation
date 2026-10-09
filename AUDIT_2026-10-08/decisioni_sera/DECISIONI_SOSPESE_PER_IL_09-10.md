# Decisioni dell'08/10 sera e punti SOSPESI per il 09/10 (coordinatore PC, Fable 5.1)

Ordine dell'utente (08/10 sera, testuale): «Procedi con: D2, D1 patch, D3: e' da strategia? se si teniamolo. D4: esporre,
D5: va bene cosi'. D6: Quelle concluse crea una sezione apposta e spostale li. D7: annullarlo. D8: lasciali fuori per ora.
D9: lascia cosi'. D10: oltre 3 gol per lato sono gli "any vari". D11: 1:si, 2:si. D11: 1: si. D13: si. D14: si tutto.
D15: scegli la soluzione migliore. PER I PUNTI RIMASTI IN SOSPESO, SCRIVI TUTTO E LI FACCIAMO DOMANI.»
Fonte dei punti: `AUDIT_2026-10-08/HANDOFF_VERIFICA_PC_E_FUSIONE.md` §6.

## 1. Decise stasera e in lavorazione (delegati Opus, referti in questa cartella)
| punto | decisione | dove | referto |
|---|---|---|---|
| D-2 | correggere: dopo un `replaceOrders` rifiutato il place-and-trim NON va a DONE; attende il sostituto nel `Trade`, altrimenti `submin_abort` e la chiusura si rifa' (scalper, sniper, tennis, worker) | `trading/submin.py` | `D2_SUBMIN_REPLACE_RIFIUTATO.md` |
| D-1 | applicare la patch: B2 con la tolleranza PER CICLO come K5 | `Betfair/stream/scalper/certificazione.py` | `BANCO_D1_D13_D14_D15.md` |
| D-4 | esporre nelle schede UI dei bot tennis le soglie di `gate-aperto` che il bot LEGGE; quelle non lette restano dichiarate | catalogo Python + schede TS tennis | `UI_D4_GATE_TENNIS_D6_CASHOUT_CONCLUSE.md` |
| D-6 | sezione «Concluse» nella pagina Cash Out: mercato CLOSED con posizioni da regolare | `frontend/src/pages/CashOut.tsx` + regole pure | idem |
| D-7 | ordine dell'app non abbinato sul lato della copertura: ANNULLATO in automatico, poi copertura sull'esposizione riletta | worker W2 | `W2_D7_ANNULLO_ORDINE_APP.md` |
| D-13 | azzerare `omega_service._LAMBDA_CACHE` fra scenari nel banco della Safe (come RB-5 di Omega), solo banco | banco Safe | `BANCO_D1_D13_D14_D15.md` |
| D-14a | `psutil` 7.2.2 e `pytest-xdist` installati nel `.venv` del PC (coordinatore, 08/10 20:05) | `.venv` | questo file |
| D-14b | `psutil` in `requirements.txt` + riga esplicita nel referto se manca | banco | `BANCO_...` |
| D-14c | scenario `riavvio` di Omega azzera TUTTI gli stati (una sola fonte di verita') | banco Omega | `BANCO_...` |
| D-14d | memoria per identita' delle liste convertite in `valuta` SOLO se dimostrata sicura al 100 % (uscite identiche) | `Betfair/stream/valuta.py` | `BANCO_...` |
| D-15 | memoria del padre di `certifica`: causa misurata e corretta nel banco, referto identico | `banco_comune.py` | `BANCO_...` |

## 2. Decise stasera SENZA codice
- **D-3 (break point nel tie-break)**: SI', e' strategia. Il cloud lo dice (`cantiere_6/REFERTO.md` §4 e §11.1: «non corretto, e' la
  strategia»; la spec dice 0-40/15-40, il bot entra anche su 0-3/1-3 del ribattitore nel tie-break). Per ordine dell'utente si TIENE:
  nessuna modifica; il controllo SP3 continua a segnalarlo nei referti (e' informazione, non un KO). Se un giorno si vuole escludere il
  tie-break, e' un cantiere suo con replay prima/dopo (cambia una decisione di trading).
- **D-5**: va bene cosi' (netto per fase calcolato sulla fase, differenza di un centesimo dichiarata a schermo).
- **D-8**: `audit-ml`, `schema-architettura`, `feature/scalper-media-under` restano FUORI da master.
- **D-9**: scalper `riavvio` B1 su 35797769 (preesistente): si lascia cosi'.
- **D-11.1** (riduzione parziale dell'utente = STOP del bot): confermato; **D-11.2** (DB illeggibile: fermo per l'intera partita):
  confermato. Nessun codice: e' il comportamento gia' in master.
- «D11: 1: si» ripetuto: letto come **D-12.1** («mercato del bot» = tutti i mercati su cui e' ARMATO): confermato, nessun codice.
  DA CONFERMARE DOMANI che la lettura sia giusta.

## 3. SOSPESI: da decidere il 09/10 (uno alla volta)
1. **D-10 (banco di Omega, cantiere 7, `cantiere_7/REFERTO.md` §8)**. L'utente ha detto: «oltre 3 gol per lato sono gli "any vari"».
   Lettura del coordinatore: oltre 3 gol per lato il Correct Score ha solo le selezioni «Any Other/Any Unquoted Home-Away-Draw», che
   da ieri Omega V3 considera candidate (`v3_include_aggregate` = True). Quindi:
   - **P1**: oggi lo scanner (`scanner.is_cs_candidate`, `CS_MAX_GOALS_SIDE = 3`) SMETTE di seguire il CS quando una squadra segna il
     4o gol, e Omega non valuta piu' la gamba 2T (35760084: dal 63', 43 valutazioni in meno). DA DECIDERE: lo scanner deve
     continuare a seguire il CS per le partite seguite da Omega, perche' restano gli «Any Other»? (E' una decisione dello scanner,
     non di Omega: cambia cosa Omega vede nel 2T; replay prima/dopo necessario; nessuna soglia di strategia toccata.)
   - **P2**: un blocco CS/HT rimasto nella riga dopo che lo scanner non lo segue piu' rende fermo il verdetto MO+CS di Omega (nessuna
     decisione finche' lo scanner non lo riprende; 35797769 `esiti-ignoti`: dal 3' al 30'). Opzioni: lo scanner toglie/marca «non
     seguito» il blocco, oppure Omega ignora nel verdetto un mercato non seguito. E' l'ordine «mai ciechi» del 01/10.
   - **P3**: prima del 30' la gamba 1T V4 decide sul REST (CS non nel feed; 35760084: 83 coppie `get_event_market_by_type`+`read_market`).
     Opzioni: sottoscrivere il CS dal fischio per le partite seguite da Omega, oppure lasciare il REST (volume REST da contare:
     regola «niente spam REST», 30/09).
2. **D-11.3** una copertura del WORKER che fa dire «ridotta» a un bot ora lo ferma: va rifiutata anche quella? (oggi: il bot si ferma).
3. **D-11.4** verita' del paper = blotter del runner paper; runner paper riavviato -> nessuna decisione (conservativo): confermare.
4. **D-11.5** annullo esterno di un ordine in attesa: Omega/Safe possono RI-PIAZZARLO, Mike si ferma. Uniformare? (proposta: come Mike).
5. **D-11.6** Safe paper sul canale (K7 preesistente): cantiere a parte, quando.
6. **D-12.3** dopo l'intervento esterno NON parte la chiusura forzata di fine finestra (posizione lasciata a mercato con CRITICAL): confermare.
7. **D-12.4** media under: all'intervento si annulla anche la banca PERSIST: confermare.
8. **D-12.5** scalper in PROVA non sa degli ordini manuali del ladder in prova (processo separato): accettare o cantiere.
9. **D-12.6** nessuna soglia minima (anche 2 EUR fermano il bot): confermare o soglia.
10. **D-12.7** durante la sospensione (verifica o DB giu') si rifiutano anche le CHIUSURE del bot su quella selezione (38 piazzamenti
    rifiutati in `db-giu`); alternativa: lasciar passare le sole chiusure (riduzione del rischio). `W3B_CONSAPEVOLEZZA_FLUMINE.md` §14.5.
11. **Cantiere 9, D2**: la stessa riga senza codice del maker anche in `sniper_bot.py:1322` e `tennis_scalper_bot.py:2850` (telemetria
    del rifiuto): fare, con replay di quei bot.
12. **Cantiere 9, D3**: resto 0,97 dopo un parcheggio rifiutato: 30 s di pausa anti-cascata scoperti (`min_bet_skip` x79). Cambiare la
    pausa e' trading: decidere.
13. **W2 §6.1**: copertura che produrrebbe «chiusa» per un bot: oggi RIFIUTATA e dichiarata; alternativa: farla partire comunque.
14. **W2 §6.2**: chiusura dal sito di una posizione di un bot e poi «chiudi» su quell'ordine: la copertura riapre l'esposizione. La
    pagina deve avvisare?
15. **Piano di architettura, 7 decisioni che bloccano la tappa 0** (`ARCHITETTURA_2026-10/05_PIANO_DI_MIGRAZIONE.md` §8.1): U-62 ora di
    Windows + PC sveglio + avvio al login; U-32 finto di Omega nel banco prima del congelamento; U-27 baseline di Mike + registrazioni
    complete; U-44 3-5 partite tennis compresse nel repo; U-37 commit dei 4 documenti non tracciati; U-59 tre normalizzazioni dell'ombra;
    U-60 misurare i 120 ms del banco.

## 4. Prima dei test PAPER e LIVE del 09/10 (promemoria dovuto, standard §1)
- Ogni bot va dichiarato «certificato sul replay» o no PRIMA di paper/live. Replay tennis dei cantieri 5, 6, 9, W3b: NON eseguiti su
  nessuna macchina (solo test): corsa unica del §3.1 dell'handoff (5 bot su 35790089 + pro e scalper su 35794049, ~5-10 min l'uno,
  in parallelo) prima del paper tennis.
- D-2 e' money-critical per scalper, sniper, tennis e worker: live su questi SOLO dopo che il referto D2 e' certificato dal coordinatore.
- Prove a schermo ancora da fare dall'utente: pagina Cash Out in PROVA (handoff §3.4), registro del replay (§3.5); migrazione
  `replay_tennis_fonte_nomi_2026-10-08.sql` (unica mancante, verificato in sola lettura 08/10 19:20).
- Dal vivo al primo avvio (solo log, nessun ordine di prova): righe `[conto-ws]`, `posizione di conto dallo stream ordini del runner`,
  `[scalper-sess] ... ordini esterni dallo stream ordini del conto` (handoff §3.7).

## 5. Aggiunte dai cantieri della sera (08/10, dopo le 20:00): da confermare il 09/10
16. **D-13, riavvio della Safe nel banco**: l'azzeramento della cache del modello (`_LAMBDA_CACHE`) vale all'ingresso e all'uscita di
    ogni scenario, NON al riavvio a meta' partita: il banco della Safe non esercita `get_event`, con cui la Safe riavviata in
    produzione ritrova il modello. Confermare che il riavvio NON azzeri (scelta del delegato, dichiarata).
17. **D-14d NON applicata** (memoria per identita' delle liste convertite in `valuta`): 60-72 % di riuso misurato, ma un riuso
    sicuro al 100 % richiede un confronto completo tipi compresi (`==` non vede 2 -> 2.0) e il guadagno sul PC non e' misurabile
    (21-49 s contro 18-52 s). Resta un'idea, non un cantiere.
18. **D-2, limite di flumine**: un parcheggio in stato REPLACING non si puo' ritirare (flumine rifiuta il cancel). Allo scadere dei
    15 s la sequenza si chiude e dichiara; un sostituto nato in ritardo entra comunque nei conti dei bot (agganciano i Trade a ogni
    book). Ritirare davvero quella gamba richiederebbe un involucro nostro di `execute_replace`: decidere se farlo.
19. **D-2, orologio del tetto**: nel banco solo lo scalper calcio sostituisce `time.time`; nei replay tennis e Mike il tetto dei 15 s
    conterebbe tempo reale (mai sollecitato nei replay). Da uniformare se si vuole esercitarlo nel banco tennis.
20. **W2/D-7, contratto «strada unica»** (`test_contratto_strada_unica_2026_09_25.py`): verde (controlla per file), ma il testo di
    motivazione cita solo `place_order`; aggiungere una riga per il `cancelOrders` del worker. La doppia conferma della pagina Cash
    Out non preannuncia l'annullo automatico: lo dice solo l'esito. Primo uso LIVE da osservare (referto W2_D7 §7).
21. **D-4, divergenza dichiarata**: lo scalper tennis LEGGE `min_total_matched` ma resta fuori dalla scheda perche' lo scenario non ne
    cambia il valore (gia' 0). Esporla o no: decidere. Le differenze numeriche fra i riferimenti tennis del 07/10 e master (es.
    swing `gate-aperto` 126 -> 116 azioni) sono dei cantieri 5/6/9 del cloud, presenti PRIMA del lavoro di stasera: da attribuire
    con la corsa unica del §3.1 dell'handoff.
22. **D-6, eccezione**: nella sezione «Concluse» lo scalper resta fermabile (il pulsante ferma la sessione, non piazza sul mercato
    chiuso). Confermare.
23. **Test di tempo ricorrente**: `frontend/src/lib/replayVerificaBarraScript.test.ts` (lancia davvero lo script con vite-node, tetto
    40 s per test) e' rosso quando la macchina e' sotto carico (4 rossi nel worktree UI con pytest in parallelo; 1 rosso nella corsa
    intera della cima fusa, 5/5 x3 da solo). Non e' un difetto del codice: proposta per domani, alzare il tetto a 90 s o eseguire
    quel file in serie (`sequence`), cosi' la suite intera e' verde anche sotto carico.
