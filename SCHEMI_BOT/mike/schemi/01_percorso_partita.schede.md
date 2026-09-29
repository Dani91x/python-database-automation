# Mike - Schema 01: il percorso di una partita (schede)

Schema: `01_percorso_partita.html` (specifica `01_percorso_partita.workflow.json`).
Fonte dei fatti: `SCHEMI_BOT/mike/inventario/B_strategia.md`.
Schede dell'inventario usate qui (vista d'insieme): 1, 5, 6, 10, 11, 13, 16, 19, 20, 21 (prima del fischio, in
breve: il dettaglio e' nello schema 02); 22-31 (uscita al fischio); 32-34 (seconda puntata); 35-38 (copertura);
39-44 (posizione coperta); 45-46 (chiusura); 47-50 (piatto e rientro); 51-52 (come si scrive un ordine);
«Percorso di una partita», tabella delle transizioni, glossario, differenze dalla Costituzione, cose strane.

**Come si legge lo schema.** Il percorso buono corre in alto da sinistra a destra: Osserva -> Giri pre-partita ->
Uscita al fischio -> Piatto -> Conti chiusi. Le corsie sotto sono le deviazioni: la protezione dopo il fischio
(seconda puntata e copertura) e il gioco fino alla fine (posizione coperta, chiusura, senza posizione).

**Colori (uguali in tutti gli schemi di Mike):** ambra = attesa; azzurro = azione, cioe' un ordine;
viola = decisione; verde = profitto bloccato; rosa = perdita o blocco; grigio = fermo o fine.

**Una regola che vale ovunque.** Di serie le uscite sono MANUALI: quando Mike decide di bancare per uscire
(green prima del fischio, uscita al fischio, cash out, uscita in perdita, green del rientro) non manda l'ordine, ma
ti mostra una proposta da approvare. Restano sempre automatiche: la copertura Over 4,5, il tetto di perdita della
partita, il ritiro degli ordini d'ingresso, il regolamento.

**I tick di Betfair usati negli esempi:** 0,01 sotto quota 2,00; 0,02 fra 2 e 3; 0,10 fra 4 e 6; 0,20 fra 6 e 10.

---

## 1. Osserva

**Cosa fa.** Mike guarda la partita e aspetta il momento per puntare. Non ha nessuna posizione aperta.

**Quando.** Da quando la partita entra nella lista del bot fino al fischio d'inizio. Dopo ogni giro chiuso
Mike torna qui.

**Numeri.** Mike puo' entrare da 1,0 ora prima del fischio. Non entra piu' da 10 minuti prima del fischio.
Dopo un giro chiuso aspetta 60 secondi prima del giro successivo.

**Esempio con le cifre.** Fischio alle 21:00. Alle 19:45 Mike scrive «fuori finestra» e aspetta. Alle 20:00 i
controlli passano e Mike punta. Alle 20:51 scrive «finestra pre-match chiusa» e non punta piu'.

**Cosa vedi nell'app.** Il motivo per cui non entra, nella scheda della partita e nell'attivita'
(per esempio «fuori finestra», «prezzo 1.25 fuori banda», «cooldown»).

**Se qualcosa va storto.** Se i dati di mercato sono vecchi Mike scrive «feed stantio» e non punta. Se al
fischio Mike e' ancora qui senza posizione, passa a «Senza posizione».

**Per il tecnico.** Casella `WATCH`. Controlli d'ingresso `_entry_guard`, `engine.py:2495-2538` (13 condizioni,
schema 02). Pausa `pre_reentry_cooldown_s`. Da `WATCH` al fischio: `engine.py:2666` -> `IDLE_LIVE`.

---

## 2. Giri pre-partita

**Cosa fa.** Mike punta l'Under 3,5 con 10 euro al miglior prezzo e subito appoggia una bancata 2 tick sotto.
Se la bancata si abbina, il giro e' chiuso con un piccolo profitto e Mike ricomincia. A 10 minuti dal fischio
decide l'ultima mossa: se e' in profitto chiude e rientra con l'ultimo ingresso; se e' in perdita tiene la
posizione fino al fischio (oppure la chiude in perdita se il veto sull'Under 3,5 lo dice).

**Quando.** Da 1 ora a 10 minuti prima del fischio, fino a 10 giri per partita.

**Numeri.** Punta 10,00 euro. Quota fra 1,30 e 3,00. Bancata 2 tick sotto il prezzo medio. Attesa massima
dell'abbinamento della punta: 60 secondi. Massimo 10 giri. Pausa fra i giri 60 secondi.

**Esempio con le cifre.** Mike punta 10,00 euro sull'Under 3,5 a 1,50. Appoggia una bancata di 10,14 euro a 1,48.
Se la bancata si abbina: con 0-3 gol vinci 5,00 - 4,87 = +0,13 euro; con 4 o piu' gol perdi 10,00 e vinci 10,14,
cioe' +0,14 euro. Il giro vale circa +0,14 euro lordi in entrambi gli esiti.

**Cosa vedi nell'app.** «ingresso ciclo 1», «ingresso abbinato», «green resting appoggiata», «ciclo 1 chiuso: +0.14».
Con le uscite manuali la bancata compare come proposta da approvare.

**Se qualcosa va storto.** Se la punta non si abbina in 60 secondi Mike la ritira e torna a Osserva. Se al
fischio resta una posizione aperta, si va a «Uscita al fischio». Se al fischio non resta niente, si va a
«Senza posizione».

**Paper o live.** In live, se spegni l'interruttore della bancata appoggiata, Mike aspetta i 2 tick e chiude al
miglior prezzo invece di appoggiare.

**Per il tecnico.** Caselle `PRE_ENTRY_PENDING`, `PRE_OPEN`, `PRE_GREEN_PENDING`, `HOLD`, `PRE_LAST_ENTRY_PENDING`.
`_decide_prematch` `engine.py:2628-2816`; `_after_entry_fill` 2819; `_cycle_done` 2835; `_after_final_green` 2858.
Ruoli `under_entry`, `under_green`, `under_last`. Dettaglio nello schema 02.

---

## 3. Uscita al fischio

**Cosa fa.** Appena la partita e' in gioco Mike ritira gli ordini non abbinati e, se ha una posizione Under 3,5,
appoggia UNA bancata 2 tick sotto il suo prezzo medio. Poi aspetta. Decide fra tre strade: la bancata si abbina
(-> Piatto), arriva un gol (-> Seconda puntata), passano 3 minuti (-> Copertura).

**Quando.** Dal momento in cui Mike vede la partita in gioco, per 3 minuti. La bancata si appoggia solo a mercato
aperto e gia' in gioco.

**Numeri.** Bancata 2 tick sotto il prezzo medio. Finestra 180 secondi. L'ultimo ingresso non abbinato resta
valido 120 secondi dal fischio di calendario, poi Mike ritira il residuo.

**Esempio con le cifre.** Posizione 10,00 euro a 1,50. Alle 21:00:40 Mike vede il gioco e appoggia 10,14 euro a
1,48. Alle 21:01:10 scrive «scade fra 150 s». Se si abbina al 2': con 0-3 gol +0,13 euro, con 4+ gol +0,14 euro,
circa +0,12 / +0,13 euro netti dopo la commissione del 5 %.

**Cosa vedi nell'app.** «in gioco: provo l'uscita a +2 tick», «uscita appoggiata a 1.48», «mercato sospeso:
aspetto la riapertura per uscire». Con le uscite manuali la bancata e' una proposta e l'orologio dei 3 minuti
corre lo stesso.

**Se qualcosa va storto.** Mercato sospeso: Mike aspetta la riapertura. Mercato chiuso: va a Copertura. Bancata
abbinata solo in parte e poi cancellata: Mike copre il residuo, non la riappoggia. I 3 minuti contano anche il
tempo a mercato sospeso: dopo una sospensione lunga la finestra risulta scaduta appena il mercato riapre.

**Per il tecnico.** Casella `LIVE_KO_GREEN`, ruolo `ko_green`. Passaggio al fischio `engine.py:2636-2666`;
`_decide_ko_green` 3001-3157; `finestra_uscita_scaduta` 2963; `piano_uscita_ko` 2984. Parametri `ko_green_ticks` 2,
`ko_green_window_s` 180, `cancel_unmatched_after_ko_s` 120. Il servizio tratta `ko_green` sempre come appoggiata
(`service.py:1330-1346`).

---

## 4. Piatto

**Cosa fa.** La posizione e' chiusa: Mike non ha piu' esposizione. Se la chiusura era in profitto e c'e' stato
esattamente 1 gol nel primo tempo, puo' tentare il rientro sull'Under 4,5. Altrimenti resta fermo fino ai conti.

**Quando.** Dopo l'uscita al fischio abbinata, oppure dopo una chiusura in gioco completata.

**Numeri.** Rientro solo dopo una chiusura in profitto, con 1 gol, entro il 45', con quota Under 4,5 piu' alta
del prezzo del primo ingresso della partita, e con almeno 10 euro disponibili.

**Esempio con le cifre.** Uscita al fischio abbinata: +0,13 euro bloccati. Al 30' e' 1-0 e l'Under 4,5 e' a
1,70, piu' di 1,50: Mike rientra. Se invece e' 0-0 o 2-0, resta fermo con +0,13 euro fino ai conti.

**Cosa vedi nell'app.** «uscita al fischio: +0.13», «chiuso (profit)», «0 gol fuori range re-ingresso»,
«oltre il minuto di re-ingresso».

**Se qualcosa va storto.** Se resta un residuo di esposizione chiudibile Mike torna a «Posizione coperta». Se il
residuo e' troppo piccolo per un ordine (sotto 0,01 euro) lo porta al regolamento.

**Per il tecnico.** Casella `FLAT`. `_decide_flat` `engine.py:3677-3708`; `residuo_non_chiudibile` 3654.
Permesso di rientro `reentry_allowed` solo con motivo «profit».

---

## 5. Rientro Under 4,5

**Cosa fa.** Mike punta l'Under 4,5 con 10 euro al miglior prezzo e appoggia una bancata 2 tick sotto. La bancata
resta sul book fino a fine partita. Una volta sola per partita.

**Quando.** Da Piatto, con le condizioni della scheda 4.

**Numeri.** Punta 10,00 euro. Bancata 2 tick sotto. Attesa massima dell'abbinamento della punta 60 secondi.
Chiusura a tempo spenta di serie (minuto limite 0).

**Esempio con le cifre.** Punta 10,00 euro sull'Under 4,5 a 1,70; bancata 10,12 euro a 1,68. Se si abbina: con
0-4 gol +7,00 - 6,88 = +0,12 euro; con 5+ gol -10,00 + 10,12 = +0,12 euro.

**Cosa vedi nell'app.** «re-ingresso Under 4.5», «re-ingresso abbinato», «re-ingresso aperto, green sul book».

**Se qualcosa va storto.** Se la bancata non si abbina, la posizione Under 4,5 va al regolamento senza
copertura, senza cash out e senza uscita in perdita (vedi «Punti da decidere»). Se Betfair cancella la bancata a
un gol, Mike la rimette alla riapertura.

**Per il tecnico.** Caselle `REENTRY_PENDING`, `REENTRY_OPEN`, `REENTRY_GREEN_PENDING`. `engine.py:3711-3808`.
Ruoli `reentry`, `reentry_green`. Parametri `reentry_*`.

---

## 6. Conti chiusi

**Cosa fa.** Quando il mercato chiude Mike ritira ogni ordine rimasto e regola la partita: calcola il risultato
di ogni puntata e bancata.

**Quando.** A mercato chiuso, da qualunque casella.

**Numeri.** Commissione 5 % sul netto positivo della partita.

**Esempio con le cifre.** Uscita al fischio abbinata (10,00 a 1,50 contro 10,14 a 1,48), partita finita 1-1:
risultato +0,13 euro lordi, circa +0,12 euro netti.

**Cosa vedi nell'app.** La partita passa fra quelle regolate con il risultato in euro.

**Se qualcosa va storto.** Una partita senza nessuna puntata viene chiusa con risultato 0.

**Per il tecnico.** Caselle `SETTLING` -> `SETTLED` (area A, non inventariata qui). Tabella delle transizioni,
ultima riga.

---

## 7. Seconda puntata

**Cosa fa.** Se arriva un gol durante l'uscita al fischio, Mike ritira la bancata d'uscita e punta di nuovo
l'Under 3,5 con meta' importo al miglior prezzo: la quota e' salita, la media migliora. Una volta sola.

**Quando.** Gol dopo il fischio, mentre l'uscita non e' ancora abbinata.

**Numeri.** Importo 50 % di 10 euro = 5,00 euro. Se in 120 secondi dal gol la puntata non si abbina, Mike la
ritira e copre tutto in una volta. Massimo 20 tentativi.

**Esempio con le cifre.** Posizione 10,00 a 1,50; gol al 2'; Mike punta 5,00 a 1,95. Totale 15,00 euro a media
1,65. Con 0-3 gol vinci +9,75 euro invece di +5,00. Con 4+ gol perdi 15,00 euro prima della copertura.

**Cosa vedi nell'app.** «gol precoce: seconda puntata sull'Under 3.5», «seconda puntata abbinata a 1.95 (media
1.65 su 15 EUR)», «seconda puntata non abbinata in tempo: copertura piena».

**Se qualcosa va storto.** Mercato sospeso o poca liquidita': Mike aspetta, ma i 120 secondi corrono. Il tetto
di rischio della partita puo' impedire la puntata: allora copre subito.

**Per il tecnico.** Casella `LIVE_SECOND_ENTRY`, ruolo `under_second`. `gol_dopo_il_fischio` `engine.py:2934`;
`momento_del_gol` 2945; `_decide_second_entry` 3160-3225. Parametri `second_entry_stake_pct` 50,
`early_goal_cover_delay_s` 120.

---

## 8. Copertura Over 4,5

**Cosa fa.** Mike compra la protezione: punta l'Over 4,5 (5 o piu' gol) per un importo che, se arrivano 5 gol,
restituisce il 120 % della perdita dell'Under. Dopo la seconda puntata la compra in due meta'.

**Quando.** Dopo 3 minuti senza uscita, dopo la seconda puntata, dopo un'uscita abbinata solo in parte, o se il
mercato chiude durante l'uscita. Non copre con 3 o piu' gol. Aspetta 45 secondi dopo ogni gol.

**Numeri.** Importo = (1,2 x rischio Under - gia' coperto) / ((quota Over - 1) x 0,95). Quota limite 2 tick sotto
il miglior prezzo. Dopo un gol precoce: prima meta' dopo 120 secondi dal gol, seconda meta' 180 secondi dopo la
prima. Riprezzo ogni 10 secondi, massimo 20 tentativi.

**Esempio con le cifre.** Rischio 10,00 euro, Over 4,5 a 6,6: Mike punta 2,26 euro con limite 6,2. Con 5+ gol:
+2,26 x 5,6 x 0,95 = +12,02, meno i 10,00 dell'Under = +2,02 euro. Con 0-3 gol: +5,00 - 2,26 = +2,74 euro lordi.
Con 4 gol: -10,00 - 2,26 = -12,26 euro.

**Cosa vedi nell'app.** «copertura Over 4.5», «copertura Over 4.5: prima tranche», «prima tranche fra 50 s (attesa
dal gol)», «copertura saltata: troppi gol», «copertura: riprezzo».

**Se qualcosa va storto.** Mercato Over 4,5 sospeso: aspetta. Poca liquidita': aspetta. Copertura non completata:
ricalcola sul gia' abbinato e riprova.

**Paper o live.** Sotto i 2 euro in live il servizio usa la sequenza «piazza e riduci» (area ordini).

**Per il tecnico.** Caselle `LIVE_UNCOVERED`, `LIVE_COVER_PENDING`, ruolo `over_cover`. `_decide_uncovered`
`engine.py:3273-3412`; `_decide_cover_pending` 3425-3498; `frazione_copertura` 3240; `attesa_prima_tranche` 3228.
Sempre automatica anche con le uscite manuali (`gate_uscite` 2337).

---

## 9. Senza posizione

**Cosa fa.** La partita e' in gioco e Mike non ha niente in mano. Non fa nulla fino ai conti.

**Quando.** Al fischio senza posizione: nessun giro aperto, oppure ultimo ingresso non fatto (spento, veto,
mercato non adatto, tetto), oppure posizione sparita.

**Numeri.** Nessuno.

**Esempio con le cifre.** Alle 20:50 il giro 3 si chiude piatto con +0,14 euro. Al fischio Mike non ha
posizione: resta fermo, la partita chiude con +0,42 euro (tre giri da +0,14).

**Cosa vedi nell'app.** Nella scheda della partita «LIVE · NESSUNA POSIZIONE».

**Se qualcosa va storto.** Punto da decidere, da confermare: se l'ultimo ingresso non si e' abbinato per niente
al fischio, Mike arriva qui SENZA ritirarlo; se si abbinasse dopo, nessuno lo gestirebbe (niente uscita, niente
copertura). Vedi «Punti da decidere» n. 1: con il tipo d'ordine di oggi l'ordine in pratica non resta vivo.

**Per il tecnico.** Casella `IDLE_LIVE`. `engine.py:2666`, `_dispatch` 2465-2470 (nessuna azione). Cose strane n. 1
dell'inventario.

---

## 10. Posizione coperta

**Cosa fa.** Mike ha l'Under e la copertura. Guarda ogni giro se chiudere tutto: in profitto (cash out), in
perdita tollerata (intervallo e secondo tempo), o al tetto di perdita. Altrimenti tiene. Dopo un gol precoce,
qui aspetta anche la seconda meta' della copertura.

**Quando.** Dopo che la copertura e' abbinata (o saltata), fino alla chiusura o alla fine.

**Numeri.** Cash out se il netto bloccabile e' almeno il 5 % del capitale investito; cash out intelligente mai
sotto il 2 %. Uscita in perdita all'intervallo o fra il 46' e l'85', solo con 3 o 4 gol, entro il 25 % del
capitale (se il modello non ha dati). Tetto di perdita 100 % del capitale.

**Esempio con le cifre.** Under 10,00 + Over 2,26 = capitale 12,26 euro, soglia 5 % = 0,61 euro. Al 40' sul 0-0 il
cash out vale +0,75 euro netti: Mike chiude. All'intervallo sul 2-1 con modello assente il cash out vale -2,50
(20 %): Mike chiude in perdita tollerata.

**Cosa vedi nell'app.** «profit: 0.75 >= 5% di 12.26», «loss tollerata (ht): ...», «tengo», «seconda tranche:
completo la copertura». Con le uscite manuali il cash out e l'uscita in perdita sono proposte; il tetto di
perdita parte da solo.

**Se qualcosa va storto.** Prezzi incompleti: Mike aspetta. Con il tetto al 100 % la chiusura scatta solo quando
non c'e' piu' niente da salvare.

**Per il tecnico.** Casella `LIVE_COVERED`. `_decide_covered` `engine.py:3511-3603`; `_loss_rule` 3501. Parametri
`cashout_profit_pct` 5, `cashout_smart_*`, `ht_loss_*`, `h2_loss_*`, `loss_exit_mode` «model», `event_loss_cap_pct` 100,
`early_goal_cover2_delay_s` 180.

---

## 11. Chiusura

**Cosa fa.** Mike banca al miglior prezzo ogni selezione aperta (Under 3,5, Over 4,5, Under 4,5) e segue gli ordini
finche' tutto e' chiuso. Ritira le bancate su selezioni gia' decise dai gol.

**Quando.** Dopo la decisione di chiudere in «Posizione coperta».

**Numeri.** Riprezzo dopo 10 secondi fermo, massimo 20 tentativi.

**Esempio con le cifre.** Cash out deciso a +0,75 euro: Mike banca l'Under 3,5 e l'Over 4,5 al miglior prezzo. La
bancata dell'Under resta ferma 10 secondi: Mike la ritira e la rimette al nuovo miglior prezzo.

**Cosa vedi nell'app.** «chiusura residuo», «chiusura: riprezzo», «chiuso (profit)», «chiusura: tentativi
esauriti».

**Se qualcosa va storto.** Con 20 tentativi esauriti Mike resta qui e lo segnala. Punto da confermare col replay:
il riprezzo di una bancata puo' non ripartire per la regola «mai due bancate a mercato» (cose strane n. 3 e 4).

**Per il tecnico.** Casella `LIVE_CLOSING`. `_decide_closing` `engine.py:3606-3651`; ruoli `under_close`, `over_close`,
`reentry_green`; `_close_actions` (area A). Passa a `FLAT`; rientro permesso solo con motivo «profit».

---

## Frecce

- Osserva -> Giri pre-partita: tutte le 13 condizioni d'ingresso sono si' (schema 02).
- Giri pre-partita -> Uscita al fischio: la partita e' in gioco, Mike ha una posizione Under 3,5 e l'uscita al
  fischio e' accesa. (Con l'uscita al fischio spenta va diretto a Copertura: freccia non disegnata.)
- Uscita al fischio -> Piatto: la bancata d'uscita si e' abbinata per intero entro la finestra.
- Piatto -> Conti chiusi: il mercato chiude.
- Piatto -> Rientro Under 4,5: chiusura in profitto, esattamente 1 gol, entro il 45', quota Under 4,5 piu' alta del
  primo ingresso, almeno 10 euro disponibili.
- Rientro Under 4,5 -> Conti chiusi: il mercato chiude (se la bancata si abbina prima, Mike torna a Piatto e da
  li' ai conti).
- Uscita al fischio -> Seconda puntata: gol dopo il fischio con uscita non abbinata; seconda puntata accesa e mai
  fatta. (Con la seconda puntata spenta: diretto a Copertura.)
- Uscita al fischio -> Copertura: 180 secondi dall'inizio del gioco visto da Mike, mercato aperto e in gioco, uscita
  non abbinata. Anche: uscita abbinata solo in parte, mercato chiuso, uscita non calcolabile.
- Seconda puntata -> Copertura: la seconda puntata si e' abbinata (anche in parte), oppure 120 secondi dal gol,
  oppure tentativi esauriti, importo nullo o tetto di rischio.
- Copertura -> Posizione coperta: la copertura e' abbinata; oppure copertura saltata (3+ gol, niente rischio, gia'
  sufficiente, tetto).
- Posizione coperta -> Chiusura: netto >= 5 % del capitale o cash out intelligente; oppure intervallo/46'-85' con 3-4
  gol e il modello (o la regola fissa del 25 %) dice di chiudere; oppure netto <= -100 % del capitale.
- Posizione coperta -> Copertura (non disegnata): 180 secondi dopo la prima meta' della copertura, per la seconda meta'.
- Chiusura -> Piatto: nessuna bancata di chiusura viva e niente esposizione residua (o tentativi finiti).
- Giri pre-partita -> Senza posizione: al fischio niente posizione (giro chiuso piatto, ultimo ingresso non fatto).
  Anche da Osserva al fischio.
- Senza posizione -> Conti chiusi: il mercato chiude.

## Punti da decidere

1. **Ultimo ingresso lasciato vivo senza posizione (da confermare).** Se al fischio l'ultimo ingresso non ha
   abbinato niente, Mike passa a «Senza posizione» senza ritirarlo, e in quella casella non lo ritira piu'
   (`engine.py:2641-2643`, 2666). Sulla carta, se si abbinasse dopo, resterebbe una posizione Under 3,5 senza
   uscita e senza copertura.
2. **L'ultimo ingresso «resta valido in gioco» solo sulla carta (da confermare).** La strategia lo chiede
   «resta in gioco» (PERSIST), ma l'ordine vero parte «cade al fischio» e «tutto o niente» sia in paper
   (`Betfair/safe_strategy/execution.py:514` persistenza fissa LAPSE, `:531` tutto o niente su ogni ordine sopra il
   minimo) sia in live (`Betfair/omega/omega_market.py:735` persistenza fissa LAPSE, `:746` tutto o niente salvo
   le bancate appoggiate). Ho letto quelle righe: confermano. Conseguenza: l'ultimo ingresso o si abbina subito
   per intero o muore; il punto 1 in pratica non puo' accadere, ma nemmeno la grazia dei 120 secondi ha oggetto.
3. **Anche la punta d'ingresso dei giri e' «tutto o niente» (da confermare).** Stesse righe del punto 2: la punta
   non resta sul book, quindi l'attesa di 60 secondi dell'abbinamento e il «tengo la parte abbinata» in pratica non
   hanno oggetto.
4. **I 3 minuti dell'uscita contano anche il tempo a mercato sospeso** (Costituzione §15.6 dice il contrario).
5. **Uscita abbinata in parte**: Mike copre subito il residuo invece di riappoggiare l'uscita (Costituzione §15.6
   caso d dice «si ri-appoggia»).
6. **Attesa «intelligente» della copertura**: in tutte le strade normali la copertura e' «ordinata» e l'attesa
   intelligente della Costituzione (Fase 3) non si applica; resta solo l'attesa di 45 secondi dopo un gol.
7. **Rientro Under 4,5 senza protezione**: mentre la bancata del rientro e' sul book non ci sono copertura, cash out
   ne' uscita in perdita. La Costituzione non ne parla.
8. **Uscita in perdita con 3-4 gol**: la Costituzione (Fase 5) dice 2, 3 o 4 gol.
9. **Tetto di perdita al 100 %**: in pratica spento.
10. **Riprezzi delle bancate** (chiusura finale pre-partita, chiusura in gioco, chiusura a tempo del rientro): per
    la regola «mai due bancate a mercato» il riprezzo puo' non partire. Da confermare col replay.
11. **Risultati mostrati non omogenei**: il giro pre-partita mostra il profitto lordo, l'uscita al fischio il netto
    dopo la commissione.
