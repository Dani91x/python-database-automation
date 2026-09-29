# Mike - Schema 03: dal fischio d'inizio alla copertura

Schema: `03_dal_fischio.html` (tipo workflow). Si legge da sinistra a destra: la riga in mezzo e' il
percorso principale (fischio -> uscita appoggiata per 3 minuti -> copertura). Sopra c'e' l'esito buono
(uscita abbinata), sotto le attese e i casi a parte, in fondo cosa succede dopo un gol.

**Schede dell'inventario usate** (`SCHEMI_BOT/mike/inventario/B_strategia.md`): 5, 22, 23, 24, 25, 26, 27, 28,
29, 30, 31, 32, 37; righe della tabella delle transizioni che partono da `LIVE_KO_GREEN`, `LIVE_SECOND_ENTRY`,
`IDLE_LIVE` e le tre righe «qualunque pre-partita». Dall'inventario dell'area ordini
(`C_servizio_e_ordini.md`): schede 16, 19, 24, 51, 52, 53; Differenze 1, 5, 9; Cose strane 1, 3.

**Colori dei riquadri** (stessa legenda degli schemi 01, 02 e 04, in basso nello schema): «Azione: ordine»
(Mike piazza o ritira ordini: fischio, uscita, gol, seconda puntata, ritiro, verso la copertura); «Decisione»
(una domanda si'/no); «Attesa»; «Profitto bloccato» (uscita abbinata); «Fermo, fine» (senza posizione).

**Parole usate**: *punta* = back; *banca* = lay; *media* = quota media della posizione Under 3,5 abbinata;
*esposizione netta* = quanto vinci o perdi sull'Under con cio' che e' gia' abbinato; *appoggiata* = banca
lasciata sul book a quota fissa finche' qualcuno non la prende; *giro* = ogni controllo del bot sulla partita
(uno ogni 0,5-2 secondi).

**Una regola che vale per tutto lo schema**: con le impostazioni di serie le uscite sono MANUALI. L'uscita al
fischio (riquadro «Appoggia l'uscita») non parte da sola: diventa una proposta nella scheda della partita, e
parte solo se la approvi. Restano sempre automatici la copertura, i ritiri degli ordini e la seconda puntata.

---

## 1. Fischio d'inizio

**Cosa fa**
- Mike vede che la partita e' passata in gioco.
- Mike ritira tutti gli ordini pre-partita non ancora abbinati (ingressi, banche di green).
- Mike NON ritira subito l'ultimo ingresso (la punta Under 3,5 da 10 euro messa a 10 minuti dal fischio): lo
  lascia per 120 secondi dal fischio di calendario, perche' puo' ancora abbinarsi (vedi riquadro 12).
- Mike guarda se ha in mano una posizione Under 3,5 abbinata.
  - Si', e l'uscita al fischio e' accesa: annota la quota Under al fischio, l'ora in cui ha visto il gioco
    (da qui partono i 3 minuti) e i gol al fischio; poi va a «Mercato pronto?».
  - Si', ma l'uscita al fischio e' spenta (o la media non e' una quota valida): va direttamente alla copertura
    Over 4,5 (schema 04).
  - No: va a «Senza posizione».

**Quando**
- Al primo giro in cui la partita risulta in gioco, da qualunque casella pre-partita: osserva, ingresso in
  coda, posizione aperta, chiusura in coda, «tengo» (posizione in perdita) o ultimo ingresso in coda.

**Numeri**
- Grazia per l'ultimo ingresso: 120 secondi dal fischio di calendario (regolabile 0-900 s).
- Uscita al fischio: accesa di serie, 2 tick sotto la media.
- Finestra dell'uscita: 180 secondi (3 minuti), contati da quando Mike vede il gioco, non dal fischio di
  calendario.

**Esempio con le cifre**
- Fischio di calendario 21:00:00. Mike vede il gioco alle 21:00:40.
- In mano: punta Under 3,5 10,00 euro a 1,50. Se l'Under vince +5,00 euro, se perde -10,00 euro.
- Mike annota: ora del gioco 21:00:40, gol al fischio 0, quota Under al fischio 1,50.
- La finestra dei 3 minuti scade alle 21:03:40.

**Cosa vedi nell'app**
- La fase della partita passa «in gioco».
- Nell'attivita': «in gioco: provo l'uscita a +2 tick», oppure «in-play con posizione Under» (uscita spenta),
  oppure «in-play senza posizione».
- Nella scheda Trade: i ritiri degli ordini pre-partita.

**Se qualcosa va storto**
- Se i gol al fischio non arrivano dal feed, Mike li annota al primo giro in cui arrivano (riquadro 4). Se non
  arrivano mai, un gol precoce NON viene riconosciuto (riquadro 8).
- Il fischio vale per quello che dice il mercato Betfair («in gioco»), non l'orario di calendario.

**Paper e live**: identico.

**Per il tecnico**: `engine.py:2636-2666` (`_decide_prematch`, ramo `snap.inplay`); grazia PERSIST 2641-2643;
`ko_price_under` 2650-2651; `live_since`/`ko_goals` 2656-2659; verso `LIVE_KO_GREEN` 2660-2663; verso
`LIVE_UNCOVERED` con `cover_forced` 2664-2665; verso `IDLE_LIVE` 2666. Parametri `cancel_unmatched_after_ko_s`,
`ko_green_enabled`, `ko_green_ticks`, `ko_green_window_s` (`config.py`). Inventario B scheda 5.

---

## 2. Mercato pronto?

**Cosa fa**
- Prima di appoggiare la banca d'uscita, Mike guarda lo stato del mercato Over/Under 3,5.
- La banca si appoggia SOLO a mercato aperto E gia' in gioco. Prima Betfair la cancellerebbe al passaggio in
  gioco.
- Domande, in ordine:
  1. Il mercato e' aperto e in gioco? Si' -> «Appoggia l'uscita».
  2. E' aperto ma non ancora in gioco? -> aspetta («Aspetta», riquadro 11).
  3. E' sospeso o in uno stato sconosciuto? -> aspetta la riapertura (riquadro 11).
  4. E' chiuso? -> niente uscita: va alla copertura (schema 04).

**Quando**
- A ogni giro nella fase «uscita al fischio», dopo aver controllato abbinamento, gol e finestra (riquadro 4).

**Numeri**
- Nessuna soglia.

**Esempio con le cifre**
- 21:00:05: il mercato e' sospeso per il fischio -> Mike aspetta, nessun ordine.
- 21:00:40: il mercato riapre in gioco -> Mike appoggia la banca 10,14 euro a 1,48.

**Cosa vedi nell'app**
- «mercato aperto ma non ancora in gioco: aspetto il passaggio in-play per appoggiare l'uscita».
- «mercato sospeso: aspetto la riapertura per uscire».
- «mercato chiuso: l'uscita al fischio non e' piu' possibile».

**Se qualcosa va storto**
- Durante la sospensione l'orologio dei 3 minuti NON si ferma: Mike solo non dichiara la scadenza finche'
  il mercato e' sospeso. Se la sospensione dura oltre i 3 minuti, alla riapertura la finestra risulta subito
  scaduta e si va alla copertura senza aver mai potuto appoggiare l'uscita (vedi «Punti da decidere» n. 1).

**Paper e live**: identico.

**Per il tecnico**: `engine.py:3074-3087` (`appoggiabile_in_gioco`, `operabile`, `riaprira`, `stato_mercato`).
Inventario B scheda 29.

---

## 3. Appoggia l'uscita

**Cosa fa**
- Mike calcola la banca d'uscita: quota = media della posizione Under arrotondata alla scala Betfair, meno 2 tick;
  importo = quello che chiude tutta l'esposizione netta (stessa vincita in tutti e due gli esiti).
- La quota e' un LIMITE: se il mercato offre di meglio, si abbina meglio, mai peggio.
- Mike appoggia UNA banca e la lascia sul book. Non la rifa' a ritmo.
- Controlli, in ordine, prima di piazzare:
  1. Il piano si puo' calcolare? No -> copertura (schema 04), «uscita al fischio non calcolabile».
  2. C'e' una banca sull'Under 3,5 a esito ignoto (Mike non sa se e' viva)? Si' -> aspetta (riquadro 11).
  3. C'e' ancora viva un'altra banca (per esempio la green pre-partita in attesa che il ritiro sia confermato)?
     Si' -> aspetta.
  4. La banca d'uscita e' gia' sul book con la stessa quota e lo stesso importo? Si' -> niente da fare.
  5. E' sul book ma quota o importo sono cambiati (per esempio si e' abbinato il resto dell'ultimo ingresso e la
     media e' cambiata)? Si' -> la ritira; la nuova parte al giro dopo.
  6. La stessa identica richiesta e' gia' stata rifiutata dal mercato? Si' -> non la ripete.
  7. Altrimenti piazza la banca.

**Quando**
- A ogni giro nella fase «uscita al fischio», con mercato aperto e in gioco (riquadro 2).

**Numeri**
- 2 tick sotto la media (regolabile 1-10).
- Finestra 180 secondi (regolabile 0-900).
- Scala dei tick Betfair: 0,01 sotto quota 2,00; 0,02 fra 2 e 3; 0,05 fra 3 e 4; 0,10 fra 4 e 6; 0,20 fra 6 e 10.
- Il parametro «ritmo di ri-presentazione» dell'uscita (5 secondi) esiste nelle impostazioni ma non viene piu'
  usato da nessun controllo.

**Esempio con le cifre**
- Posizione: punta 10,00 euro a 1,50. Vincita se l'Under vince +5,00; perdita se perde -10,00.
- Quota d'uscita: 1,50 meno 2 tick = 1,48.
- Importo: (5,00 + 10,00) / 1,48 = 10,135 -> 10,14 euro di banca a 1,48.
- Se si abbina: Under vince -> +5,00 - 10,14 x 0,48 = +0,13 euro; Under perde -> -10,00 + 10,14 = +0,14 euro.
  Netto della commissione del 5 % circa +0,12 / +0,13 euro.
- Alle 21:01:10 l'app dice che l'uscita scade fra 150 secondi.

**Cosa vedi nell'app**
- Nella scheda Trade la banca «uscita al fischio: 2 tick sotto 1.50».
- Attivita': «uscita appoggiata a 1.48», con i secondi che restano della finestra.
- Con le uscite manuali (serie): una PROPOSTA d'uscita da approvare. L'orologio dei 3 minuti corre anche mentre
  non approvi.

**Se qualcosa va storto**
- Rifiuto del mercato: Mike non ripropone la stessa identica banca; ne fa una nuova solo se cambia quota o importo.
- Prezzi non vivi (feed fermo): nessun ordine parte, nemmeno le chiusure (fatto nuovo, vedi «Punti da decidere»
  n. 6). L'orologio dei 3 minuti corre lo stesso.
- Gol durante l'uscita: il mercato si sospende e Betfair fa cadere la banca non abbinata (vedi riquadro 11 per
  cosa succede alla riapertura).

**Paper e live**: la banca e' appoggiata in tutti e due. In paper la esegue il simulatore (runner); in live va a
Betfair e resta sul book.

**Per il tecnico**: `engine.py:2984-2998` (`piano_uscita_ko`, `compute_greenup`); `engine.py:3089-3157`
(controlli 1: 3090-3093; 2: 3106-3114; 3: 3115-3118; 4: 3119-3124; 5: 3125-3127; 6: 3143-3149; 7: 3150-3157).
Ruolo della gamba `ko_green`; nel servizio e' sempre «resting» (`service._is_resting_leg`). Parametro non letto:
`ko_green_retry_s` (`config.py:173`). Inventario B schede 25, 30; C schede 24, 35.

---

## 4. Controllo del giro

**Cosa fa**
- A ogni giro nella fase «uscita al fischio», Mike si fa le domande in QUESTO ordine e si ferma alla prima che
  ha risposta si':
  0. Ho ancora una posizione Under? No -> ritira tutto, «Senza posizione» (riquadro 10).
  0-bis. (sempre) Ritira il resto dell'ultimo ingresso se sono passati 120 s dal fischio (riquadro 12).
  0-ter. Se mancano l'ora del gioco o i gol al fischio, li annota adesso.
  1. L'ultima banca d'uscita ha abbinato qualcosa e non e' piu' sul book? Si' -> «Uscita abbinata» (riquadro 7).
  2. C'e' stato un gol dopo il fischio? Si' -> «Gol precoce» (riquadro 8).
  3. Sono passati i 3 minuti? Si' -> «Finestra scaduta» (riquadro 5).
  4. Altrimenti -> guarda il mercato (riquadro 2) e appoggia o tiene l'uscita (riquadro 3).
- Cosa NON fa in questa fase: nessuna uscita in perdita, nessun cash out, nessuna copertura finche' non
  succede una delle cose sopra o il mercato chiude.

**Quando**
- A ogni giro (circa ogni 0,5-2 secondi) finche' la partita e' nella fase «uscita al fischio».

**Numeri**
- Gol dopo il fischio = gol adesso maggiori dei gol annotati al fischio. Se uno dei due numeri manca, la
  risposta e' NO (meglio perdere la seconda puntata che inventarsi un gol).

**Esempio con le cifre**
- 21:01:50, 0-0, banca 10,14 a 1,48 sul book non abbinata, mancano 110 s -> nessuna risposta si': tiene l'uscita.
- 21:02:10, 1-0 -> domanda 2: gol -> «Gol precoce».
- Se alle 21:02:10 la banca fosse abbinata per 4,00 euro e il gol l'avesse fatta cadere, risponde si' la
  domanda 1 (abbinata in parte) PRIMA della 2: Mike copre il resto, niente seconda puntata.

**Cosa vedi nell'app**
- Attivita' «uscita a +2 tick sul book» mentre aspetta.
- Il riquadro successivo scrive il suo motivo.

**Se qualcosa va storto**
- Gol sconosciuti al fischio (feed muto al calcio d'inizio): un gol precoce non viene mai visto; l'uscita resta
  fino alla scadenza dei 3 minuti, poi copertura piena.

**Paper e live**: identico.

**Per il tecnico**: `engine.py:3001-3060` (`_decide_ko_green`: S<=0 3003-3005; `_late_persist_cancel` 3006;
`live_since`/`ko_goals` 3008-3011; A 3019-3035; C 3037-3050; B 3052-3060); `gol_dopo_il_fischio` 2934-2942.
Inventario B schede 22, 26, 27, 31.

---

## 5. Finestra scaduta

**Cosa fa**
- Se sono passati 3 minuti di gioco senza abbinamento e senza gol, Mike ritira la banca d'uscita e passa alla
  copertura piena sull'Over 4,5 (schema 04).
- Domande per dire «scaduta»:
  1. Mike sa da quando c'e' gioco? No -> non scaduta.
  2. Il mercato Under 3,5 e' in questo momento aperto e in gioco? No -> non scaduta (ma l'orologio continua).
  3. Sono passati almeno 180 secondi dall'ora in cui ha visto il gioco? Si' -> scaduta.

**Quando**
- A ogni giro nella fase «uscita al fischio», dopo le domande su abbinamento e gol.

**Numeri**
- 180 secondi (regolabile 0-900).

**Esempio con le cifre**
- Gioco visto alle 21:00:40. Alle 21:03:40, mercato aperto in gioco, banca 10,14 a 1,48 ancora non abbinata ->
  Mike la ritira e va alla copertura.
- Stesso caso ma alle 21:03:40 mercato sospeso: non scaduta. Riapre alle 21:04:30: scaduta subito.
- Esito dopo la copertura (schema 04): Over 4,5 a 6,6 -> punta 2,26 euro. 0-3 gol: +5,00 - 2,26 = +2,74 lordi;
  4 gol: -12,26; 5+ gol: circa +2,02 netti.

**Cosa vedi nell'app**
- Attivita': «uscita non abbinata in 3': copertura Over 4.5», voce dell'uscita al fischio con esito «scaduta».

**Se qualcosa va storto**
- Sospensione lunga (VAR, infortunio): la finestra conta anche il tempo sospeso (vedi «Punti da decidere» n. 1).

**Paper e live**: identico.

**Per il tecnico**: `engine.py:2963-2981` (`finestra_uscita_scaduta`), `3052-3060` (strada B, `cover_forced` =
vero). Inventario B schede 24, 28; Differenze 6.

---

## 6. Verso la copertura

**Cosa fa**
- E' il punto d'arrivo di questo schema: Mike passa alla fase «da coprire» e la copertura Over 4,5 la decide
  lo schema 04.
- Ci si arriva da sette strade, tutte con la copertura «ordinata» (Mike non fa l'attesa intelligente,
  aspetta solo i 45 secondi dopo un gol):
  1. finestra dei 3 minuti scaduta (riquadro 5) -> copertura piena;
  2. uscita abbinata solo in parte (riquadro 7) -> copertura del resto;
  3. gol precoce con seconda puntata spenta o gia' fatta (riquadro 8) -> copertura piena;
  4. seconda puntata abbinata (riquadro 9) -> copertura in due tranche;
  5. seconda puntata non abbinata entro 120 s dal gol, o non piazzabile (riquadro 9) -> copertura piena;
  6. mercato Under 3,5 chiuso, o uscita non calcolabile (riquadri 2 e 3) -> copertura piena;
  7. uscita al fischio spenta dalle impostazioni (riquadro 1) -> copertura piena.

**Quando**
- Subito, nello stesso giro della decisione. La puntata Over 4,5 parte al giro dopo.

**Numeri**
- Fattore di copertura 1,2; quota limite 2 tick sotto il miglior prezzo; tranche 50 % dopo un gol (dettagli
  nello schema 04).

**Esempio con le cifre**
- Finestra scaduta con punta Under 10,00 a 1,50, Over 4,5 a 6,6: copertura 12,00 / (5,6 x 0,95) = 2,26 euro,
  limite 6,2.

**Cosa vedi nell'app**
- La partita passa in fase «copertura». I motivi sono quelli dei riquadri di provenienza.

**Se qualcosa va storto**
- Con un ordine a esito ignoto sulla partita, la copertura (che per Mike e' un'«apertura») viene tolta a ogni
  giro finche' la riconciliazione non chiarisce (vedi riquadro 11 e «Punti da decidere» n. 3).

**Paper e live**: identico.

**Per il tecnico**: arrivo in `LIVE_UNCOVERED` con `cover_forced` = vero: `engine.py:2664-2665`, `3034-3035`,
`3048-3050`, `3057-3060`, `3085-3087`, `3091-3093`, `3179-3184` (fase 1), `3190-3200` (fase 0). Schema 04 per il
seguito (`_decide_uncovered` 3273).

---

## 7. Uscita abbinata

**Cosa fa**
- Se l'ultima banca d'uscita ha abbinato qualcosa e non e' piu' sul book:
  - abbinata per INTERO (nessuna selezione resta aperta): Mike blocca il profitto, chiude la partita come
    «profitto», permette il rientro sull'Under 4,5 (schema 05), azzera i tentativi;
  - abbinata solo IN PARTE (il resto e' caduto o e' stato ritirato): Mike copre il resto sull'Over 4,5
    (schema 04). NON rimette la banca per il resto, anche se la finestra dei 3 minuti e' ancora aperta.

**Quando**
- A ogni giro nella fase «uscita al fischio»; e' la PRIMA domanda (prima del gol e della finestra).

**Numeri**
- Profitto mostrato = netto della commissione del 5 %.

**Esempio con le cifre**
- Intera: banca 10,14 a 1,48 abbinata al 2' -> «uscita al fischio: +0.13» (Under vince +0,13 lordi, perde +0,14
  lordi; circa +0,12 / +0,13 netti).
- In parte: abbinati 4,00 euro su 10,14, poi il gol fa cadere il resto. Esposizione: vince +5,00 - 4,00 x 0,48 =
  +3,08; perde -10,00 + 4,00 = -6,00. La copertura si calcola sui 6,00 euro di rischio: con Over a 6,6 ->
  7,20 / (5,6 x 0,95) = 1,35 euro.

**Cosa vedi nell'app**
- «uscita al fischio: +0.13» e voce dell'uscita con esito «abbinata»; la partita passa «chiusa».
- Oppure «uscita al fischio parziale: copro il residuo».

**Se qualcosa va storto**
- La banca abbinata in parte e poi caduta per un gol porta alla copertura, non alla seconda puntata: il gol in
  quel caso non viene piu' guardato.

**Paper e live**: identico nel bot. In live, dopo una sospensione, sapere se la banca e' «abbinata in parte»
dipende dalla rilettura alla riapertura (riquadro 11).

**Per il tecnico**: `engine.py:3019-3035` (strada A; intera: `FLAT`, `close_reason` = «profit»,
`reentry_allowed` = vero, `locked_pnl`; parziale: `LIVE_UNCOVERED` con `cover_forced`). Inventario B schede 27,
31; Differenze 7.

---

## 8. Gol precoce

**Cosa fa**
- Se c'e' un gol dopo il fischio mentre l'uscita e' ancora scoperta:
  - Mike ritira la banca d'uscita se e' ancora sul book;
  - annota il momento del gol: l'ora data dal feed, se e' fra 0 e 15 minuti fa; altrimenti adesso;
  - seconda puntata accesa e mai fatta -> «Seconda puntata» (riquadro 9);
  - altrimenti -> copertura piena sull'Over 4,5 (schema 04).

**Quando**
- A ogni giro nella fase «uscita al fischio», dopo aver visto che l'uscita non e' abbinata.

**Numeri**
- Il momento del gol conta se ha al massimo 900 secondi (15 minuti) e non e' nel futuro.
- Da quel momento partono i 120 secondi della seconda puntata e della prima tranche di copertura.

**Esempio con le cifre**
- Gol all'1-0 dichiarato dal feed alle 21:02:05; Mike lo vede alle 21:02:08 -> momento del gol 21:02:05.
- Gol dichiarato 20 minuti fa (o fra 10 secondi): momento del gol = adesso.

**Cosa vedi nell'app**
- «gol precoce: seconda puntata sull'Under 3.5», oppure «gol precoce: copertura Over 4.5».
- Voce dell'uscita al fischio con esito «gol».

**Se qualcosa va storto**
- Gol sconosciuti al fischio: nessun gol precoce viene riconosciuto (riquadro 4).
- Con il gol il mercato si sospende: in live la banca d'uscita caduta puo' risultare «esito ignoto» alla
  riapertura (riquadro 11); in quel caso la seconda puntata e la copertura vengono trattenute (vedi «Punti da
  decidere» n. 3).

**Paper e live**: identico nel bot.

**Per il tecnico**: `engine.py:3037-3050` (strada C); `gol_dopo_il_fischio` 2934-2942; `momento_del_gol`
2945-2960 (`early_goal_at`); `second_entry_enabled`, `second_entry_done`. Inventario B schede 22, 23, 27.

---

## 9. Seconda puntata

**Cosa fa**
- Dopo un gol precoce Mike punta ancora l'Under 3,5 con meta' della puntata, al miglior prezzo. La quota e'
  salita col gol, quindi la media migliora.
- Non deve mai ritardare la copertura: passati 120 secondi dal gol si copre comunque.
- Domande in ordine («tempo finito» = 120 s dal momento del gol):
  1. Ho ancora una posizione Under? No -> ritira tutto, «Senza posizione».
  2. (sempre) Ritira il resto dell'ultimo ingresso se sono passati 120 s dal fischio (riquadro 12).
  3. La seconda puntata ha abbinato qualcosa e non e' piu' sul book? Si' -> copertura A TRANCHE (schema 04).
  4. E' sul book e il tempo e' finito? -> la ritira, copertura piena.
  5. E' sul book e c'e' tempo? -> aspetta.
  6. Nessuna puntata sul book e tempo finito? -> copertura piena.
  7. Tentativi esauriti (20)? -> copertura piena.
  8. Mercato sospeso, quota non valida o manca il book? -> aspetta.
  9. Importo = 50 % della puntata. Sotto 0,01 euro? -> copertura piena.
  10. Importo oltre il tetto di esposizione per partita? -> copertura piena.
  11. Liquidita' al miglior prezzo minore dell'importo? -> aspetta.
  12. Altrimenti: punta Under 3,5 per l'importo al miglior prezzo; tentativi +1.

**Quando**
- A ogni giro nella fase «seconda puntata», dopo un gol precoce. Una volta sola per partita.

**Numeri**
- 50 % della puntata (regolabile 0-200 %): con la puntata di serie 10,00 euro -> 5,00 euro.
- 120 secondi dal gol (regolabile 0-900).
- Massimo 20 tentativi (contatore condiviso con altre fasi, vedi «Punti da decidere» n. 7).
- Tetto di esposizione per partita: 0 = spento (serie).

**Esempio con le cifre**
- Prima: 10,00 a 1,50. Dopo l'1-0 l'Under 3,5 e' a 1,95: Mike punta 5,00 a 1,95.
- Posizione: 15,00 euro a media 1,65 ((10 x 1,50 + 5 x 1,95) / 15).
- Se l'Under vince: +5,00 + 4,75 = +9,75 lordi (invece di +5,00). Se perde: -15,00 (invece di -10,00), per questo
  segue la copertura a tranche.

**Cosa vedi nell'app**
- «seconda puntata 5.00 EUR a 1.95», poi «seconda puntata abbinata a 1.95 (media 1.65 su 15.00 EUR)».
- Oppure «seconda puntata non abbinata in tempo: copertura piena», «... non piazzabile ...», «... tentativi
  esauriti», «seconda puntata: mercato sospeso», «seconda puntata: liquidita X < Y».

**Se qualcosa va storto**
- La seconda puntata parte «tutto o niente» (area ordini): se non si abbina subito e' annullata, e al giro dopo
  Mike la ripropone (qui non c'e' il controllo «richiesta gia' rifiutata») fino ai 120 s o ai 20 tentativi.
- Prezzi non vivi: nessun ordine parte (fatto nuovo n. 6).
- Con un ordine a esito ignoto sulla partita la seconda puntata viene tolta (e' un'«apertura»).
- Con il bot fermo la seconda puntata NON e' spenta dal servizio (inventario C, Differenze 13).

**Paper e live**: identico nel bot.

**Per il tecnico**: `engine.py:3160-3225` (`_decide_second_entry`; 1: 3166-3168; 2: 3169; 3: 3174-3184;
4: 3186-3193; 5: 3194; 6: 3198-3200; 7: 3201-3203; 8: 3204-3207; 9: 3208-3211; 10: 3212-3214; 11: 3215-3217;
12: 3218-3225). Ruolo `under_second`, `second_entry_stake_pct`, `early_goal_cover_delay_s`,
`close_max_attempts`. Inventario B scheda 32; C scheda 24.

---

## 10. Senza posizione

**Cosa fa**
- In gioco senza nessuna posizione Under: Mike non fa niente fino a mercato chiuso, poi regola i conti.
- Ci si arriva: al fischio senza niente in mano (riquadro 1); oppure durante l'uscita al fischio o la seconda
  puntata, se la posizione risulta zero (in quel caso Mike ritira tutti gli ordini).

**Quando**
- Dal primo giro in gioco senza posizione Under abbinata.

**Numeri**
- Nessuno.

**Esempio con le cifre**
- Tutti i cicli pre-partita chiusi in green (+0,14 euro ciascuno), ultimo ingresso non fatto: al fischio Mike e'
  «senza posizione». Se la partita non ha mai avuto ordini, alla chiusura del mercato risultato 0,00 euro.

**Cosa vedi nell'app**
- «in-play senza posizione» o «nessuna posizione Under»; card «LIVE · NESSUNA POSIZIONE».

**Se qualcosa va storto**
- Caso delicato: ultimo ingresso (punta Under 10,00) ancora sul book al fischio e mai abbinato, cicli precedenti
  chiusi. Mike va «senza posizione» e NON lo ritira (c'e' la grazia di 120 s), e in questa fase non controlla
  piu' niente. Se l'ordine si abbinasse dopo, resterebbe una posizione Under senza uscita e senza copertura.
  Secondo l'area ordini pero' l'ultimo ingresso parte «tutto o niente» e non resta mai sul book, quindi il
  caso non si presenterebbe (da confermare; vedi «Punti da decidere» n. 4).

**Paper e live**: identico.

**Per il tecnico**: `engine.py:2666` (dal fischio), `3003-3005`, `3166-3168` (posizione zero, `_cancel_live`);
`_dispatch` 2465-2470 (nessuna azione in `IDLE_LIVE`; con nessuna gamba -> `SETTLED`). Inventario B schede 5, 26,
Cose strane 1.

---

## 11. Aspetta

**Cosa fa**
- Mike resta nella fase «uscita al fischio» senza piazzare niente, nei casi:
  1. mercato aperto ma non ancora in gioco;
  2. mercato sospeso o in stato sconosciuto;
  3. una banca sull'Under 3,5 e' a esito ignoto (Mike non sa se e' viva): aspetta la riconciliazione, mai una
     banca nuova su un dubbio;
  4. un'altra banca e' ancora viva (per esempio la green pre-partita di cui si aspetta la conferma del ritiro):
     mai due banche sul mercato.
- Riprende al primo giro in cui il motivo sparisce.

**Quando**
- A ogni giro, dopo le domande su abbinamento, gol e finestra.

**Numeri**
- Nessuno. L'orologio dei 3 minuti continua a correre.

**Esempio con le cifre**
- Gol al 2': il mercato si sospende con la banca 10,14 a 1,48 sul book. Alla riapertura Mike rilegge l'ordine:
  - paper: il simulatore applica la regola di Betfair, la banca risulta caduta senza abbinamento -> Mike vede il
    gol e va alla seconda puntata;
  - live: se la banca non e' piu' fra gli ordini correnti, l'esito e' SEMPRE «ignoto» e la gamba va in
    riconciliazione (vedi sotto).

**Cosa vedi nell'app**
- «mercato sospeso: aspetto la riapertura per uscire».
- «uscita '...' a esito ignoto: aspetto la riconciliazione, mai una gamba nuova su un dubbio».
- «attendo l'annullamento della lay precedente».
- Alla riapertura: «rilettura alla riapertura», «ordine scaduto alla sospensione», oppure «riapertura esito
  ignoto».

**Se qualcosa va storto**
- FATTO NUOVO (a), verificato nel codice del servizio: in live, alla riapertura dopo una sospensione, una banca
  appoggiata sparita dagli ordini correnti da' sempre «esito ignoto» e la gamba va in riconciliazione. Motivo:
  lo sportello di produzione verso Betfair non sa leggere un ordine per numero di scommessa. Conseguenza (mia
  deduzione, da confermare col replay): finche' l'esito resta ignoto Mike non piazza nessuna «apertura», cioe'
  ne' la seconda puntata ne' la copertura Over 4,5. Vedi «Punti da decidere» n. 2 e n. 3.

**Paper e live**: la regola del bot e' identica. Diverso l'esito della rilettura: in paper la caduta alla
sospensione si applica sempre; in live, per una banca non piu' fra i correnti, l'esito e' ignoto.

**Per il tecnico**: `engine.py:3075-3083` (aperto non in gioco, sospeso/ignoto), `3106-3118` (`in_volo`,
`needs_reconcile`, `altre_lay`); guardia `has_unknown_orders` -> `_strip_openings` 2189-2191 (ruoli d'apertura
`OPENING_ROLES` riga 50, comprende `under_second` e `over_cover`). Rilettura alla riapertura: `service.py`
2872-2962 (`_sorveglia_sospensione`), 2423-2507 (`_rileggi_ordine_appoggiato`: `getattr(market,
"order_state_by_bet_id")` a 2492, «mercato_senza_lettura» a 2496; `_RealMarket` 120-228 non la definisce),
2510-2604 (reazioni). Inventario C schede 51-53, Differenze 9, Cose strane 3.

---

## 12. Ritira il residuo

**Cosa fa**
- Passati 120 secondi dal fischio di calendario, Mike ritira la parte non abbinata dell'ultimo ingresso (la punta
  Under 3,5 messa a 10 minuti dal fischio). La parte gia' abbinata resta ed entra nella posizione.

**Quando**
- All'inizio di ogni giro nelle fasi: uscita al fischio, seconda puntata, da coprire, coperta.
- NON nelle fasi: senza posizione, copertura in coda, chiusura in corso, posizione chiusa.

**Numeri**
- 120 secondi dal fischio di calendario (regolabile 0-900).

**Esempio con le cifre**
- Fischio di calendario 21:00:00. Alle 21:02:00 l'ultimo ingresso ha abbinato 6,00 euro su 10,00 -> Mike ritira i
  4,00 euro restanti. Se la banca d'uscita era calcolata su una posizione diversa, al giro dopo Mike la ritira e
  la rimette con la nuova media (riquadro 3, controllo 5).

**Cosa vedi nell'app**
- Il ritiro nella scheda Trade.

**Se qualcosa va storto**
- Secondo l'area ordini l'ultimo ingresso, anche se segnato «resta in gioco», parte come ordine «tutto o niente»
  che cade al fischio: nessun residuo puo' esistere, e questo ritiro in pratica non trova mai niente. Verificato
  da me in paper (il comando al simulatore parte con persistenza «cade al fischio» e «tutto o niente»); per il live
  da confermare. Vedi «Punti da decidere» n. 4.

**Paper e live**: identico nel bot.

**Per il tecnico**: `engine.py:3415-3422` (`_late_persist_cancel`, ruolo `under_last`,
`cancel_unmatched_after_ko_s`); chiamato in 3006, 3169, 3277 e in `_decide_covered`. Canale paper:
`Betfair/safe_strategy/execution.py:514` (`persistence="LAPSE"`), 531-533 (FOK). Live: `omega_market.py:735,746`
(non letto da me). Inventario B scheda 37; C scheda 24, Differenze 1.

---

## Frecce

Nello schema:
- Fischio d'inizio -> Mercato pronto?: in gioco con posizione Under abbinata > 0 e uscita al fischio accesa.
- Mercato pronto? -> Appoggia l'uscita: mercato Over/Under 3,5 aperto e gia' in gioco.
- Appoggia l'uscita -> Controllo del giro: a ogni giro (circa ogni 0,5-2 s) finche' la fase dura.
- Controllo del giro -> Finestra scaduta: nessun abbinamento e nessun gol dopo il fischio.
- Finestra scaduta -> Verso la copertura: almeno 180 s dall'ora del gioco con mercato aperto in gioco; ritira
  l'uscita; copertura piena.
- Fischio d'inizio -> Senza posizione: in gioco con posizione Under = 0 (nessun abbinamento).
- Mercato pronto? -> Aspetta: mercato aperto non ancora in gioco, sospeso o sconosciuto.
- Appoggia l'uscita -> Ritira il residuo: ultimo ingresso ancora sul book e almeno 120 s dal fischio di
  calendario.
- Controllo del giro -> Uscita abbinata: l'ultima banca d'uscita ha abbinato > 0 e non e' piu' sul book.
- Uscita abbinata -> Verso la copertura: abbinata solo in parte (resta esposizione aperta).
- Controllo del giro -> Gol precoce: gol adesso > gol al fischio (entrambi noti).
- Gol precoce -> Seconda puntata: seconda puntata accesa e mai fatta in questa partita.
- Seconda puntata -> Verso la copertura: abbinata (copertura a tranche), oppure 120 s dal gol senza
  abbinamento, 20 tentativi, importo nullo o tetto (copertura piena).

Fuori dallo schema (solo nelle schede):
- Fischio d'inizio -> Verso la copertura: posizione > 0 e uscita al fischio spenta (o media non valida).
- Mercato pronto? -> Verso la copertura: mercato chiuso.
- Appoggia l'uscita -> Verso la copertura: piano d'uscita non calcolabile.
- Gol precoce -> Verso la copertura: seconda puntata spenta o gia' fatta.
- Controllo del giro / Seconda puntata -> Senza posizione: posizione Under = 0; ritira tutti gli ordini.
- Appoggia l'uscita -> Aspetta: banca Under 3,5 a esito ignoto, o altra banca ancora viva.
- Senza posizione -> conti chiusi: mercato chiuso; senza nessun ordine mai fatto, risultato 0,00 euro.

---

## Punti da decidere

1. **I 3 minuti contano anche il tempo sospeso** (Costituzione §15.6 dice che la finestra «non scorre» quando non
   si puo' appoggiare). Il codice non ferma l'orologio: evita solo di dichiarare la scadenza mentre il mercato e'
   sospeso. Con una sospensione lunga la finestra risulta scaduta appena il mercato riapre. `engine.py:2979-2981`.
2. **FATTO NUOVO (a) - in live, riapertura = esito ignoto.** Verificato da me nel codice: alla riapertura, se la
   banca appoggiata non e' piu' fra gli ordini correnti, il servizio cerca di rileggerla per numero di scommessa,
   ma lo sportello di produzione non ha quella lettura: l'esito e' sempre «ignoto» e la gamba va in
   riconciliazione (`service.py:2491-2496`; `_RealMarket` non definisce `order_state_by_bet_id`). Il caso della
   Costituzione «scaduta: si ri-appoggia se la finestra e' aperta» in live non si raggiunge. Da confermare: che
   il mercato di produzione passato a quella funzione sia sempre `_RealMarket`, e quanto tempo prende la
   riconciliazione.
3. **Esito ignoto blocca seconda puntata E copertura** (mia deduzione dal codice, da confermare col replay):
   con una gamba a esito ignoto il bot toglie ogni «apertura», e per Mike sono aperture anche la seconda puntata
   e la copertura Over 4,5 (`engine.py:50`, `2189-2191`). Unita al punto 2: dopo un gol con la banca d'uscita sul
   book, in live la posizione (15,00 euro con la seconda puntata, o 10,00 senza) puo' restare scoperta finche'
   la riconciliazione non chiarisce. Da decidere se la copertura debba restare permessa anche con un esito ignoto.
4. **Ultimo ingresso «resta in gioco» che non resta**: la strategia lo segna «resta in gioco» e prevede la grazia
   di 120 s e il ritiro del residuo; l'area ordini dice che parte «tutto o niente» e cade al fischio
   (verificato da me solo per il paper). Se e' cosi', i riquadri 10 (caso delicato) e 12 non scattano mai; se un
   giorno l'ordine restasse davvero in gioco, il caso del riquadro 10 (posizione abbinata dopo il fischio senza
   uscita ne' copertura) diventerebbe reale.
5. **Uscita abbinata in parte: niente ri-appoggio** (Costituzione §15.6 caso d: «si ri-appoggia se la finestra e'
   aperta»). Il codice copre subito il resto. `engine.py:3032-3035`.
6. **FATTO NUOVO (c) - prezzi non vivi = nessun ordine**, chiusure e coperture comprese, in paper e in live
   (verificato da me: `service.py:709-717`; per la banca appoggiata l'area ordini indica `_run_event:4464-4477`,
   non letto da me). La Costituzione §5 diceva «chiusure permesse». Nella fase dell'uscita al fischio vuol dire:
   con il feed fermo l'uscita non parte e l'orologio dei 3 minuti corre.
7. **Contatore dei tentativi condiviso**: lo stesso contatore serve ai riprezzi pre-partita, alla seconda puntata
   e alla copertura, e non si azzera entrando nella seconda puntata: dopo molti riprezzi pre-partita la seconda
   puntata puo' avere meno di 20 tentativi.
8. **Seconda puntata e bot fermo**: con il bot fermo il servizio spegne ingressi, rientro e ultimo ingresso, ma
   non la seconda puntata (inventario C, Differenze 13; non verificato da me).
9. **Uscite manuali e orologio**: con le uscite manuali (serie) la banca d'uscita e' una proposta; se non la
   approvi entro i 3 minuti, la finestra scade e Mike copre.
10. **Parametro inutilizzato**: «ritmo di ri-presentazione dell'uscita» (5 s) e' nelle impostazioni ma non governa
    piu' niente.
