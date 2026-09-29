# Mike - Schema 06: uscite manuali e automatiche (schede)

Schema: `06_uscite_manuali_e_automatiche.html` (specifica `06_uscite_manuali_e_automatiche.workflow.json`).
Fonti dei fatti: `SCHEMI_BOT/mike/inventario/A_calcoli_e_guardie.md`, `C_servizio_e_ordini.md`,
`E_schermate_e_pulsanti.md`, `B_strategia.md`; ogni punto del cancello riletto nel codice (`engine.py:2164-2431`,
`service.py:3181-3250` e `3283-3393`, `avvio_app.py:173-328`, `PropostaUscitaMike.tsx`).
Schede dell'inventario usate qui:
- A: 96 (chiusura manuale in corso), 97 (ordine dei controlli di ogni giro), 98-107 (il cancello), 108 (regolamento),
  49, 50, 53, 56 (quali regole producono un'uscita), 84-87 (chiusure), 122 (`uscite_automatiche`),
  Differenze 1, Cose strane 4, 10, 19.
- C: 56 (richieste dall'app), 57 (controllo «e' per questa partita?»), 58 (approvazione), tabella dei ruoli
  (uscite discrezionali), Differenze 11.
- E: 17 (riquadro «Se chiudo tutto ora»), 18 (Cash out), 19 (Chiudi a mercato), 20 (Annulla ordini), 22 (Riprendi),
  23 e 34 (proposta d'uscita), 28 e 29 (interruttore delle uscite), 35 (Chiudi della Control Room),
  tabella dei parametri (`uscite_automatiche`).
- B: introduzione punto 1, schede del green prima del fischio e dell'uscita al fischio, Cose strane 12.

**Come si legge lo schema.** Il percorso principale corre da sinistra a destra: Mike vuole uscire -> interruttore
-> e' un'uscita gia' partita? -> proposta a video -> approvi -> firma valida? -> Mike esegue. In alto a destra le uscite
che non passano mai dal cancello. In basso cosa succede se non rispondi.

**Colori (uguali in tutti gli schemi di Mike):** ambra = attesa; azzurro = azione, cioe' un ordine; viola =
decisione; rosa = perdita o blocco; grigio = pulsante dell'utente.

**Il giro di Mike.** Mike ridecide ogni partita in continuazione: al massimo una decisione ogni 0,5 secondi per
partita, un giro completo tipico circa ogni 2 secondi. «Al giro dopo» vuol dire, di solito, entro 2 secondi.

---

## 01. Mike vuole uscire

**Cosa fa.** La strategia di Mike decide di bancare per uscire da una posizione. Le uscite che passano dal cancello
sono cinque:
1. green prima del fischio (banca Under 3,5 due tick sotto il prezzo d'ingresso);
2. uscita al fischio (banca Under 3,5 due tick sotto, per 180 secondi dal fischio);
3. cash out in profitto, pieno (5 % della base) o anticipato (cash out intelligente);
4. uscita in perdita all'intervallo o nel secondo tempo (dal 46' all'85'), a modello o a regola fissa;
5. green del rientro sull'Under 4,5, compresa la sua chiusura a tempo se impostata.

**Quando.** A ogni giro, in qualunque fase della partita in cui c'e' una posizione.

**Numeri.** Nessun numero proprio: i numeri sono quelli delle regole d'uscita (schemi 02, 03, 05, 11).

**Esempio con le cifre.** Minuto 63', 1-0. Mike ha punta Under 3,5 10,00 euro a 2,00 e punta Over 4,5 2,10 euro a
6,00. Base del cash out 12,10 euro. L'Under si banca a 1,85 e l'Over a 6,40. Chiudendo tutto adesso Mike blocca circa
+0,64 euro netti (5,3 % della base). La soglia e' 5 % di 12,10 = 0,61 euro. Mike vuole fare cash out.

**Cosa vedi nell'app.** Niente, finche' il cancello non ha deciso chi esegue.

**Se qualcosa va storto.** Se prima del cancello un altro controllo toglie l'ordine (mai due bancate sulla stessa
selezione, ordine a esito ignoto), la proposta non nasce in quel giro.

**Per il tecnico.** Ruoli delle uscite discrezionali `USCITE_DISCREZIONALI` = `under_green`, `ko_green`,
`under_close`, `over_close`, `reentry_green` (`engine.py:2225`). Categorie `categoria_uscita` (`engine.py:2251-2262`):
`green_pre`, `ko_green`, `chiusura` (cash out e uscite in perdita), `reentry_green`. Motivi di chiusura: `profit`,
`loss_ht`, `loss_2t`, `loss_cap`, `reentry_time`. Il cancello e' l'ultimo controllo di `decide`
(`engine.py:2216`), dopo `_freno_copertura`, `_una_sola_lay`, `_mai_sovracopertura`.

---

## 02. Sempre automatiche

**Cosa fa.** Queste azioni non chiedono mai la tua firma, con l'interruttore in qualunque posizione:
1. la copertura Over 4,5 (e i suoi riprezzi);
2. il tetto di perdita della partita (chiusura forzata quando il netto arriva a -100 % della base);
3. il ritiro degli ordini d'ingresso non abbinati (ingresso, ultimo ingresso, seconda puntata, rientro);
4. il regolamento a mercato chiuso (con il ritiro di tutti gli ordini vivi);
5. la chiusura che chiedi tu con Chiudi, Cash out o Chiudi a mercato (riquadro 11);
6. il ritiro di tutto quando la partita va in errore.

**Quando.** A ogni giro in cui la decisione non contiene un'uscita delle cinque del riquadro 01, oppure il motivo e'
il tetto di perdita.

**Numeri.** Tetto di perdita della partita 100 % della base (ammesso 0-500 %). Con 100 % scatta solo quando il netto
di chiusura e' -100 % della base, cioe' quando non resta quasi niente da salvare.

**Esempio con le cifre.** Base 12,10 euro. Il tetto scatta se chiudere tutto vale -12,10 euro o meno: Mike banca tutto
senza chiedere. Una copertura Over 4,5 da 2,10 euro a 6,00 parte senza chiedere.

**Cosa vedi nell'app.** Gli ordini compaiono direttamente in «Ordini sul book» e nell'attivita'. Nessuna proposta.

**Se qualcosa va storto.** Se c'era una proposta viva, in quel giro la proposta decade (riquadro 10).

**Per il tecnico.** `MOTIVI_PROTEZIONE = ("loss_cap",)` (`engine.py:2229`); `_CANCEL_SEMPRE` = `under_entry`,
`under_last`, `under_second`, `reentry` (`engine.py:2237`); la copertura ha ruolo `over_cover`, fuori da
`USCITE_DISCREZIONALI`; regolamento in `_dispatch` (`engine.py:2435-2491`); chiusura manuale `_decide_flatten`
(`engine.py:2180-2181`, ritorna PRIMA del cancello). Parametro `event_loss_cap_pct` 100.

---

## 03. Interruttore

**Cosa fa.** Decide chi esegue le cinque uscite del riquadro 01. Manuale: Mike propone e tu approvi. Automatico: Mike
esegue da solo, come prima del 25/09.

**Quando.** Mike legge l'interruttore a ogni giro, dai parametri salvati: un cambio vale dal giro dopo, senza fermare
il bot.

**Numeri.** Di serie MANUALE. Se il valore manca o non e' leggibile, vale MANUALE. A ogni avvio NUOVO dell'app
l'interruttore torna MANUALE da solo (verificato nel codice: `avvio_app.uscite_a_manuali`, chiamata da Mike con
`uscite_bot="mike"`). Un riavvio del solo servizio dentro lo stesso avvio dell'app (il servizio caduto e
rialzato) non lo tocca.

**Esempio con le cifre.** Ieri sera hai messo Automatico. Stamattina riapri l'app: l'interruttore e' di nuovo Manuale e
l'attivita' di Mike lo scrive («uscite riportate a manuali»). Il cash out da +0,64 euro diventa una proposta.

**Cosa vedi nell'app.** L'interruttore «Uscite automatiche»: sulla riga di Mike in Control Room e nel pannello
Parametri (gruppo «Uscite HT / 2T»). Per passare ad Automatico serve un secondo clic su «confermi? passa ad automatiche»,
premibile solo dopo 0,4 secondi (contro il doppio clic). Tornare a Manuale e' un clic solo.

**Se qualcosa va storto.** Se passi ad Automatico con una proposta a video, al giro dopo Mike esegue l'uscita da solo
e la proposta sparisce.

**Per il tecnico.** `engine.uscite_automatiche` (`engine.py:2243-2248`); parametro `uscite_automatiche` default False
(`config.py:254`); reset all'avvio `Betfair/stream/avvio_app.py:173-214` e `:275-303`, chiamato da
`service.ferma_al_nuovo_avvio` (`service.py:3396-3423`). Migrazioni `uscite_manuali_default_2026-09-25.sql`,
`uscite_automatiche_mike_2026-09-25.sql`.

---

## 04. Gia' partita?

**Cosa fa.** Se l'uscita e' il seguito di un'uscita gia' partita, Mike la esegue senza chiedere di nuovo. Seguito
vuol dire: riprezzo di una bancata, residuo di un abbinamento parziale, bancata riappoggiata dopo un ritiro.

**Quando.** L'uscita e' gia' partita se vale almeno una di queste due:
- la partita e' gia' in una fase di chiusura in corso (chiusura, green del rientro in attesa, green prima del
  fischio in attesa)?
- nel giro di trading di adesso esiste gia' una bancata dello stesso tipo d'uscita (viva, abbinata o gia'
  ritirata)?

**Numeri.** Nessuno.

**Esempio con le cifre.** Hai approvato il cash out: Mike banca l'Under 10,81 euro a 1,85. Se ne abbina 6,00 euro e il
resto va riprezzato 10 secondi dopo, il riprezzo parte senza una nuova firma.

**Cosa vedi nell'app.** Nessuna proposta nuova: vedi i riprezzi nell'attivita'.

**Se qualcosa va storto.** Un'uscita partita PRIMA che tu spegnessi l'interruttore viene finita da Mike senza firma.
Una firma sul green prima del fischio vale per tutto quel giro di trading: le bancate successive dello stesso giro
partono da sole.

**Per il tecnico.** `_uscita_gia_in_corso` (`engine.py:2269-2285`); `STATI_USCITA_IN_CORSO` = `LIVE_CLOSING`,
`REENTRY_GREEN_PENDING`, `PRE_GREEN_PENDING` (`engine.py:2234`); confronto per ruolo, ciclo `cycle_no`, gamba non
archiviata.

---

## 05. Proposta a video

**Cosa fa.** Mike non manda l'ordine d'uscita. Scrive una proposta nella scheda della partita. Gli ordini che la
decisione conteneva vengono tutti tolti, tranne i ritiri degli ordini d'ingresso. Se la decisione portava a una fase
di chiusura, Mike resta nella fase di prima. Gli orologi della strategia continuano a correre (per esempio i 180
secondi dell'uscita al fischio).

**Quando.** Uscita nuova, interruttore Manuale, nessuna firma valida per quell'uscita.

**Numeri.** La proposta mostra:
- il titolo «Mike vorrebbe uscire: ...» (green-up pre-partita, uscita al fischio, cash out della posizione, uscita del
  re-ingresso), con «(in perdita)» e bordo rosso se il motivo e' un'uscita in perdita;
- il motivo scritto da Mike;
- ogni ordine proposto: tipo, banca, importo, quota della decisione, e accanto le quote di adesso (punta / banca) con
  la fonte (al millisecondo, oppure dati della partita);
- «chiudendo ora»: quanto bloccheresti adesso;
- «alla decisione»: quanto bloccavi quando Mike ha deciso (numero fermo);
- «deciso N s fa» e il minuto di gioco;
- il bollino di freschezza dei dati.
La proposta si riscrive solo se cambia l'uscita (tipo, ordini per tipo e lato, motivo). Se cambiano solo quote e
importi, la proposta resta com'era: si muove solo «chiudendo ora».

**Esempio con le cifre.** «Mike vorrebbe uscire: cash out della posizione. profit: 0.64 >= 5.0% di 12.10. Chiusura
Under banca 10,81 a 1,85 + chiusura Over banca 1,97 a 6,40. Chiudendo ora +0,64 euro, alla decisione +0,64 euro,
deciso 0 s fa, 63'.»

**Cosa vedi nell'app.** Il riquadro ambra (rosso se in perdita) sotto la scheda della partita nella pagina di Mike, e
lo stesso riquadro dentro la scheda della partita in Control Room.

**Se qualcosa va storto.** Con i dati fermi o di eta' sconosciuta il pulsante «approva uscita» e' spento («feed fermo o
ignoto: non si approva su prezzi vecchi»).

**Per il tecnico.** Ramo «si PROPONE» di `gate_uscite` (`engine.py:2380-2431`); campi `chiave`, `categoria`,
`ciclo`, `stato`, `stato_voluto`, `motivo`, `close_reason`, `ordini`, `bloccabile` (netto del cash out), `urgente`
(motivo che inizia con «loss»), `minuto`, `gol`, `decided_at` (fermo finche' la chiave e' la stessa), `proposed_at`,
`sostanza` = [chiave, (ruolo, lato) per ordine, close_reason]. Memoria `mike_events.ctx.uscita_proposta`.
Schermata `frontend/src/components/controlroom/PropostaUscitaMike.tsx`.

---

## 06. Approvi

**Cosa fa.** Premi «approva uscita». L'app manda la tua firma a Mike con la chiave della proposta e cio' che vedevi
(quota vista, quota della decisione, eta' dei dati, fonte, ora del clic). Mike NON piazza niente in quel momento:
scrive la firma nella memoria della partita. L'ordine parte al giro dopo (riquadro 07).

**Quando.** Quando premi il pulsante, con dati freschi.

**Numeri.** Un solo clic, nessuna doppia conferma, nemmeno in live. Nessun pulsante «rifiuta».

**Esempio con le cifre.** Premi alle 20:03:40. Messaggio: «approvazione inviata: parte al prossimo giro del bot». La
firma porta l'ora 20:03:40 e vale fino alle 20:05:40.

**Cosa vedi nell'app.** Il messaggio di esito; poi, sotto, la striscia che segue l'abbinamento degli ordini usciti.
Nell'attivita' la riga «uscita approvata».

**Se qualcosa va storto.** Mike rifiuta la firma e lo scrive:
- nessuna proposta viva: «Nessuna uscita in attesa di approvazione su questa partita»;
- la proposta e' cambiata nel frattempo: «La proposta e' cambiata: guarda quella nuova prima di approvare»;
- invio fallito: «approvazione non inviata: motivo»;
- richiesta senza la chiave della proposta: il database la respinge prima ancora di arrivare a Mike.
In paper e in live funziona allo stesso modo: la modalita' e' quella della partita.

**Per il tecnico.** Richiesta `approva_uscita` (`mike_request`, migrazione `uscite_automatiche_mike_2026-09-25.sql`);
`_request_approva_uscita` (`service.py:3216-3250`) scrive `ctx.uscita_approvata` = {`chiave`, `at`, `request_id`,
`contesto`}; codici `proposta_non_viva`, `proposta_cambiata`. `_id_approvazione`, `_approvazione_eseguita`,
`_chiave_gamba` (`service.py:3181-3213`): il numero della richiesta va solo sulle bancate d'uscita.

---

## 07. Firma valida?

**Cosa fa.** Al giro dopo la firma Mike ricontrolla. L'uscita parte solo se tutte e tre le risposte sono si':
1. la firma e' per la stessa uscita (stesso tipo e stesso giro di trading)?
2. la firma ha al massimo 120 secondi?
3. il motivo di adesso e' lo stesso della proposta che hai visto (per esempio «profitto» e non «perdita»)?

**Quando.** A ogni giro in cui la strategia vuole ancora la stessa uscita.

**Numeri.** Durata di una firma 120 secondi, contati dal CLIC, non da quando e' apparsa la proposta. Non si cambia
dall'app. Una firma vale una volta sola: appena usata, firma e proposta si cancellano.

**Esempio con le cifre.** Firma alle 20:03:40, giro dopo alle 20:03:42: tipo uguale, 2 secondi, motivo uguale -> parte.
Se alle 20:03:42 il motivo fosse diventato «perdita all'intervallo», la firma cade e Mike mostra la proposta nuova.

**Cosa vedi nell'app.** Se passa: la proposta sparisce e compaiono gli ordini. Se il motivo e' cambiato: una proposta
nuova, da firmare di nuovo.

**Se qualcosa va storto.** I 120 secondi contano solo se Mike non ridecide la partita per 2 minuti dopo il clic (per
esempio dati fermi). Passati i 120 secondi la firma non vale piu' e bisogna firmare di nuovo.

**Per il tecnico.** `_approvazione_valida` (`engine.py:2288-2295`), `APPROVAZIONE_TTL_S = 120.0`
(`engine.py:2240`, copiata in `Betfair/stream/uscite_proposte.py`); `_stessa_uscita_firmata` (`engine.py:2298-2310`,
confronta `close_reason`); `chiave_uscita` = «categoria|cN» (`engine.py:2265`); consumo `engine.py:2368-2379`
(telemetria `uscita_eseguita_su_approvazione`); firma d'altra uscita `engine.py:2419-2429`
(`uscita_firmata_non_eseguita`).

---

## 08. Mike esegue

**Cosa fa.** Mike manda ESATTAMENTE la decisione della strategia di adesso: quote e importi del momento, non quelli
della proposta. Da qui l'uscita segue le regole di sempre: riprezzi ogni 10 secondi, fino a 20 tentativi, senza nuove
firme (riquadro 04).

**Quando.** Al giro dopo la firma (di solito entro 2 secondi); subito se l'interruttore e' Automatico; subito se e' il
seguito di un'uscita gia' partita.

**Numeri.** Riprezzo delle chiusure 10 secondi; tentativi massimi 20; cash out alla quota migliore (0 tick di
spostamento); green e uscita al fischio 2 tick sotto l'ingresso.

**Esempio con le cifre.** Firmi dopo 40 secondi. Nel frattempo l'Under e' sceso a 1,84. Mike banca l'Under 10,87 euro a
1,84 e l'Over 1,97 euro a 6,40: blocca circa +0,70 euro netti, non i +0,64 della proposta.

**Cosa vedi nell'app.** Gli ordini in «Ordini sul book», l'attivita', e le righe d'uscita marcate con il numero della
tua approvazione.

**Se qualcosa va storto.** Le regole di sempre: prezzi non vivi, interruttore dei soldi veri spento in live, freno
unico: vedi schema 08. Un ordine rifiutato dal mercato non viene riproposto identico.
In paper e in live il cancello e' identico; cambia solo chi abbina l'ordine (vedi schema 07).

**Per il tecnico.** `engine.py:2368-2379`; `close_retry_s` 10, `close_max_attempts` 20, `cashout_place_at_ticks` 0,
`pre_green_ticks` 2, `ko_green_ticks` 2, `reentry_green_ticks` 2; `approvazione_id` sulle gambe
(`service.py:4425-4430`, `4497`, `4515`, `4527`).

---

## 09. Nessuna risposta

**Cosa fa.** Se non premi niente, nessun ordine d'uscita parte. Mike continua a seguire la partita e continua a fare
tutto cio' che e' automatico (riquadro 02). Non esiste un tempo massimo della proposta.

**Quando.** Finche' la proposta e' viva.

**Numeri.** Cosa succede per ogni tipo d'uscita:
- green prima del fischio: la bancata non va sul book; la posizione arriva al fischio e diventa uscita al fischio
  (proposta nuova);
- uscita al fischio: i 180 secondi corrono lo stesso; finiti, Mike passa alla copertura Over 4,5, che e' automatica;
- cash out in profitto: la posizione resta aperta e il profitto puo' sparire;
- uscita in perdita (intervallo, 46'-85'): la posizione resta aperta fino alla fine; resta solo il tetto di perdita
  della partita (100 %, in pratica spento);
- green del rientro: la punta sull'Under 4,5 resta aperta fino alla fine.

**Esempio con le cifre.** All'intervallo, 2-1 (3 gol), chiudere vale -2,40 euro su base 12,10 (-19,8 %, dentro il
25 % tollerato). Mike propone «uscita in perdita» (rosso). Non rispondi. Al 70' arriva il 4° gol: la posizione perde
circa 10,00 euro sull'Under meno cio' che la copertura restituisce con 5 gol o piu'. Nessuno stop e' scattato.

**Cosa vedi nell'app.** La proposta resta a video con «deciso N s fa» che cresce.

**Se qualcosa va storto.** Questa e' la decisione aperta dell'utente: in manuale, senza risposta, le uscite in perdita
non scattano (vedi «Punti da decidere»).

**Per il tecnico.** `gate_uscite` tiene solo `keep` = ritiri `_CANCEL_SEMPRE` (`engine.py:2410`); stato invariato se
la decisione portava a `LIVE_CLOSING`/`PRE_GREEN_PENDING`/`REENTRY_GREEN_PENDING`/`FLAT` (`engine.py:2413-2417`);
orologi aggiornati comunque (`engine.py:2348-2352`). Nessun `decided_at` massimo nella schermata.

---

## 10. Proposta decade

**Cosa fa.** La proposta sparisce da sola. Con lei cade anche la firma, se c'era.

**Quando.** La proposta decade se vale una di queste:
- la strategia non vuole piu' uscire (per esempio il cash out e' tornato sotto la soglia)?
- l'interruttore e' passato ad Automatico (Mike esegue da solo)?
- il motivo e' diventato il tetto di perdita della partita (Mike esegue da solo)?
La firma cade anche se Mike propone un'uscita diversa (altro tipo o altro giro di trading) o lo stesso tipo con
un altro motivo.
NON la fanno decadere: il passare del tempo; il cambio di quote o importi.

**Numeri.** Nessuno.

**Esempio con le cifre.** Proposta di cash out a +0,64 euro alle 20:03:00. Alle 20:04:10 l'Under risale a 1,90: il
cash out vale +0,37 euro, sotto 0,61. Mike non vuole piu' uscire: la proposta sparisce. Se alle 20:06:00 premi su una
pagina vecchia, Mike risponde «Nessuna uscita in attesa di approvazione». Se invece il cash out resta sopra soglia
per tutti i 3 minuti, la proposta e' ancora li' («deciso 180 s fa»): premi alle 20:06:00 e la firma vale (i 120
secondi partono dal clic); Mike esce al giro dopo ai prezzi delle 20:06.

**Cosa vedi nell'app.** Il riquadro sparisce. L'attivita' registra la decadenza una volta.

**Se qualcosa va storto.** Se la proposta ricompare poco dopo (prezzi che oscillano intorno alla soglia) e' una
proposta nuova: una firma data prima non vale.

**Per il tecnico.** `_decadi` (`engine.py:2317-2334`), telemetria `uscita_proposta_decaduta`; chiamata in
`engine.py:2356-2362`; firma per altra chiave `engine.py:2420-2421`.

---

## 11. Chiudi o Cash out

**Cosa fa.** Chiudi tu tutta la partita quando vuoi, senza proposta e senza firma: Under 3,5, Over 4,5 ed eventuale
rientro insieme. Mike prima ritira tutti gli ordini sul book, poi banca la posizione di ogni selezione ancora viva,
con i riprezzi. Prima del fischio, dopo questa chiusura Mike non rientra finche' non premi «Riprendi».

**Quando.** Pulsanti «Cash out» e «Chiudi a mercato» nella scheda della partita di Mike; «Chiudi» su una riga di Mike
in Control Room (chiude l'intera partita, non la sola riga).

**Numeri.** In live: doppia conferma, l'armamento decade dopo 10 secondi. In Control Room: nessuna doppia conferma;
se non arriva un esito entro 180 secondi la fase diventa «esito ignoto». Riprezzi ogni 10 secondi, massimo 20
tentativi.

**Esempio con le cifre.** Vedi la proposta di uscita in perdita a -2,40 euro ma vuoi chiudere subito: premi «Chiudi a
mercato», il dialogo mostra -2,40 euro, confermi due volte (live). Messaggio: «Flatten: annullati 1 ordini sul book,
chiusura in corso (netto stimato -2.40 EUR).»

**Cosa vedi nell'app.** Il dialogo col netto di chiusura; poi l'esito sotto il riquadro «Se chiudo tutto ora»; le
bancate marcate «manuale».

**Se qualcosa va storto.** Mike rifiuta se: la partita non e' seguita o e' finita; la richiesta e' per un altro bot o
per l'altra modalita' (paper e live non si mischiano); mancano le quote; i dati sono vecchi (oltre 20 secondi) e la
lettura diretta da Betfair non riesce; non c'e' niente da chiudere. Dopo 20 tentativi Mike resta in attesa senza
riprezzare.

**Per il tecnico.** Richieste `cashout` / `flatten` (`service.py:3077-3178`), controllo `service.py:3032-3074`,
`_request_flatten` (`service.py:3283-3393`: ritiro, `flatten_pending`, `close_reason` «manual», `no_reentry`
prima del fischio); guida della chiusura `_decide_flatten` (`engine.py:2077-2161`), ruolo `manual_close`, fuori dal
cancello. Schermate `MikeCashOutButton.tsx`, `MikeMatchCard.tsx:344-490`, `chiudiRiga.ts`, `BottoneChiudiRiga.tsx`.

---

## Frecce

- Mike vuole uscire -> Interruttore: la decisione contiene green prima del fischio, uscita al fischio, cash out,
  uscita in perdita o green del rientro, e il motivo non e' il tetto di perdita.
- Mike vuole uscire -> Sempre automatiche: la decisione contiene solo copertura, ritiri d'ingresso, regolamento,
  chiusura chiesta da te, oppure il motivo e' il tetto di perdita (-100 % della base).
- Interruttore -> Gia' partita?: interruttore Manuale (di serie; torna Manuale a ogni avvio nuovo dell'app).
- Interruttore -> Mike esegue: interruttore Automatico; una proposta rimasta a video decade.
- Gia' partita? -> Mike esegue: fase di chiusura gia' in corso, oppure bancata dello stesso tipo gia' presente nel
  giro di trading.
- Gia' partita? -> Proposta a video: uscita nuova.
- Proposta a video -> Approvi: premi «approva uscita» con dati freschi.
- Approvi -> Firma valida?: al giro dopo (di solito entro 2 secondi).
- Firma valida? -> Mike esegue: stessa uscita, firma di 120 secondi o meno, stesso motivo.
- Firma valida? -> Proposta a video (non disegnata): motivo cambiato o firma oltre 120 secondi: si firma di nuovo.
- Proposta a video -> Nessuna risposta: nessun clic.
- Nessuna risposta -> Proposta decade: la strategia non vuole piu' uscire, oppure interruttore Automatico, oppure
  tetto di perdita.
- Chiudi o Cash out -> Mike esegue: subito, con doppia conferma in live nella pagina di Mike.

---

## Punti da decidere

1. **Costituzione rimasta indietro.** La Costituzione di Mike (par. 15.7-ter) dice che le proposte da approvare sono
   annullate e che «le uscite di Mike restano automatiche». Il codice le tiene MANUALI di serie e le riporta a
   manuali a ogni avvio nuovo dell'app. E' la decisione permanente dell'utente: va aggiornata la Costituzione, non il
   codice.
2. **Nessuna rete di perdita in manuale.** In manuale, se non rispondi, le uscite in perdita (intervallo, 46'-85') non
   scattano e non c'e' un tempo massimo. Resta solo il tetto di perdita della partita a 100 % della base, che in pratica
   non scatta mai. Decisione aperta: una rete automatica di perdita si' o no, e a quale cifra.
3. **La firma e l'importo.** La firma controlla tipo, giro di trading e motivo, non quote e importi: Mike esegue ai
   prezzi del giro dopo il clic. Se in quei 1-2 secondi la proposta si riscrive con ordini diversi (per esempio si
   aggiunge la chiusura del rientro) ma lo stesso motivo, la firma vale lo stesso. Da decidere se basta.
4. **I 120 secondi.** Contano dal clic, non dalla comparsa della proposta: una proposta vecchia di 3 minuti si firma
   ancora. Non c'e' un tempo massimo per la proposta e la costante non si cambia dall'app.
5. **Un'uscita partita prima dello spegnimento** viene finita da Mike senza firma (riquadro 04): voluto, ma va
   saputo. Stesso per le bancate successive dello stesso giro di trading dopo una firma sul green prima del fischio.
6. **Commento sbagliato nel codice.** Il testo di `gate_uscite` dice «interruttore ACCESO (default)»
   (`engine.py:2340`); il default vero e' SPENTO, cioe' manuale (`engine.py:2247`, `config.py:254`).
7. **Tutti gli altri ordini tolti.** Quando Mike propone, toglie tutti gli ordini della decisione tranne i ritiri
   d'ingresso: se una decisione contenesse un'uscita e una copertura insieme, anche la copertura non partirebbe.
   Oggi non e' stato trovato un ramo che lo faccia (inventario A, Cose strane 10).
8. **Tetto di perdita dietro le uscite in perdita.** Nella posizione coperta Mike valuta prima cash out, poi uscita
   in perdita, poi tetto di perdita. Se l'uscita in perdita scatta (proposta, non eseguita) il tetto non viene
   guardato in quel giro. Con il tetto a 100 % oggi non ha effetto; conta se il tetto viene abbassato. Da verificare.
9. **Veto dell'Under 3,5 con proposta non firmata.** Se l'uscita finale prima del fischio (col veto) resta proposta e
   non la firmi, la posizione entra in gioco e il veto risulta comunque «scattato» (inventario B, Cose strane 12).
10. **Proposta a video durante una tua chiusura.** Mentre la chiusura chiesta con Chiudi o Cash out e' in corso Mike
    non passa dal cancello: una proposta rimasta a video resta visibile e firmabile, ma la firma non fa niente; sparisce
    al primo giro dopo la fine della chiusura. Letto nel codice, non provato.

## Punti non chiariti

- Gli importi degli esempi (10,81, 1,97, 10,87) sono calcolati a mano con la formula della chiusura a quota
  migliore e la commissione 5 % sul netto positivo di ogni mercato: arrotondati al centesimo.
- Il passaggio «finiti i 180 secondi dell'uscita al fischio Mike passa alla copertura» viene dall'inventario B, non
  riletto riga per riga.
