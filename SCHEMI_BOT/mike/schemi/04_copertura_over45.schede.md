# Mike - Schema 04: la copertura sull'Over 4,5

Schema: `04_copertura_over45.html` (tipo workflow). Si legge da sinistra a destra: la riga in mezzo e' il
percorso principale (serve coprire? -> attesa -> quanto comprare -> punta Over 4,5 -> sul book -> coperta).
Sopra c'e' la seconda tranche (solo dopo un gol precoce), sotto le rinunce, le attese e i freni.

**Schede dell'inventario usate** (`SCHEMI_BOT/mike/inventario/B_strategia.md`): 33, 34, 35, 36, 38, 44; righe
della tabella delle transizioni che partono da `LIVE_UNCOVERED` e `LIVE_COVER_PENDING` (e la riga `LIVE_COVERED`
«fase 2 e 180 s»); premessa punto 2 (freno sui rifiuti: massimo 3 rifiuti con lo stesso codice, minimo 15 secondi
fra due tentativi; «mai sovracopertura»); Differenze 8, 9, 12. Dall'inventario dell'area ordini
(`C_servizio_e_ordini.md`): schede 16, 18, 19, 20, 22, 24, 25, 55, 56; Differenze 5; Cose strane 1, 2, 24.

**Colori dei riquadri** (stessa legenda degli schemi 01, 02 e 03, in basso nello schema): «Azione: ordine»
(punta Over 4,5, riprezzo); «Decisione» (serve coprire?, quanto comprare); «Attesa» (attesa dal gol, sul book,
aspetta, posizione coperta, seconda tranche); «Perdita o blocco» (niente copertura, freno rifiuti).

**Parole usate**: *punta* = back; *rischio Under* = quanto perdi sull'Under 3,5 se finisce con 4 o piu' gol,
tolto cio' che le banche gia' abbinate hanno chiuso; *gia' coperto* = quanto rendono netto, con 5 o piu' gol, le
punte Over 4,5 gia' abbinate; *tranche* = una parte della copertura; *giro* = ogni controllo del bot sulla partita
(uno ogni 0,5-2 secondi).

**Una regola che vale per tutto lo schema**: la copertura e' SEMPRE automatica, anche con le uscite manuali di
serie. Non e' una proposta: Mike la compra da solo.

**Cosa protegge la copertura**: con l'Under 3,5 in mano, 0-3 gol = vinci; 4 gol = perdi l'Under e la copertura;
5 o piu' gol = l'Over 4,5 paga 1,2 volte la perdita dell'Under, cioe' chiudi in utile del 20 % del rischio.

---

## 1. Serve coprire?

**Cosa fa**
- Mike decide se la copertura si compra, si rimanda o non si compra. Domande nell'ordine esatto del codice
  (la prima che risponde decide):
  1. Ho ancora una posizione Under 3,5? No -> ritira tutto, «senza posizione» (schema 03).
  2. (sempre) Ritira il resto dell'ultimo ingresso se sono passati 120 s dal fischio (schema 03, riquadro 12).
  3. Sono in copertura a tranche ma non so piu' quando c'e' stato il gol (per esempio dopo un riavvio)? Si' ->
     copre tutto in una volta.
  4. La copertura e' spenta nelle impostazioni? Si' -> «Niente copertura» (riquadro 8).
  5. Prima tranche e non sono ancora passati 120 s dal gol? Si' -> «Attesa dal gol» (riquadro 2).
  6. Ci sono piu' di 2 gol (3 o piu')? Si' -> «Niente copertura».
  7. Il rischio Under e' zero o meno? Si' -> «Niente copertura».
  8. Il mercato Over/Under 4,5 e' sospeso, chiuso o sconosciuto? Si' -> «Aspetta» (riquadro 9).
  9. Sono nei 45 secondi dopo un gol, o manca la quota Over? Si' -> «Attesa dal gol».
  10. L'importo da comprare e' sotto 0,01 euro? Si' -> «Niente copertura» («copertura gia' sufficiente»).
  11. Altrimenti -> «Quanto comprare» e «Punta Over 4,5».

**Quando**
- A ogni giro nella fase «da coprire». Ci si arriva dallo schema 03 (finestra scaduta, gol precoce, seconda
  puntata, uscita abbinata in parte, mercato chiuso, uscita spenta), da una copertura non completata (riquadro 5)
  e dalla seconda tranche (riquadro 7).

**Numeri**
- Massimo gol per coprire: 2 (regolabile 0-4). Con 3 o piu' gol niente copertura.
- Copertura accesa di serie.

**Esempio con le cifre**
- 0-0 al 4', punta Under 10,00 a 1,50, Over 4,5 a 6,6, mercato aperto: tutte le risposte no fino alla 11 ->
  compra.
- 2-1 al 30' (3 gol): «copertura saltata: troppi gol», la posizione resta senza copertura: con un altro gol
  (4 gol) perdi 10,00 euro, con 0 gol in piu' vinci +5,00 lordi.

**Cosa vedi nell'app**
- I motivi dei riquadri di arrivo. Nel diario la voce «copertura» quando compra e «attesa copertura» quando
  aspetta.

**Se qualcosa va storto**
- Con un ordine a esito ignoto sulla partita (per esempio la banca d'uscita dopo una sospensione in live) la
  copertura viene tolta a ogni giro: per Mike e' un'«apertura». Vedi «Punti da decidere» n. 2.

**Paper e live**: identico.

**Per il tecnico**: `engine.py:3273-3368` (`_decide_uncovered`; 1: 3274-3276; 2: 3277; 3: 3282-3283; 4: 3284-3286;
5: 3287-3293; 6: 3340-3342; 7: 3343-3345; 8: 3353-3359; 9: 3360-3365; 10: 3366-3368); `cover_timing` 1212-1251
(«skip» se gol > `cover_max_goals`). Stato `LIVE_UNCOVERED`. Inventario B scheda 35.

---

## 2. Attesa dal gol

**Cosa fa**
- Mike rimanda la copertura in due casi:
  1. **Prima tranche dopo un gol precoce**: aspetta 120 secondi dal momento del gol prima di comprare la prima
     meta'.
  2. **Riprezzo dopo un gol**: nei 45 secondi dopo un gol qualsiasi (con almeno 1 gol in partita) aspetta,
     perche' subito dopo il gol la quota Over crolla e coprire costa di piu'.
- Aspetta anche se manca la quota Over (nessun miglior prezzo valido).
- L'attesa «intelligente» della Costituzione (0 gol, fino a 10 minuti, rischio di gol basso, Over sotto 7,0,
  risparmio atteso almeno 8 %) nel flusso normale NON si applica: tutte le strade che portano qui arrivano con la
  copertura «ordinata», e con la copertura ordinata resta solo l'attesa dei 45 secondi.

**Quando**
- A ogni giro nella fase «da coprire».

**Numeri**
- Attesa della prima tranche: 120 secondi dal gol (regolabile 0-900).
- Attesa dopo un gol: 45 secondi (regolabile 0-300).
- Attesa intelligente (inattiva nel flusso normale): 10 minuti, rischio di gol 6 %, probabilita' di 4 gol 16 %,
  quota buona 7,0, risparmio minimo 8 %.

**Esempio con le cifre**
- Gol alle 21:05:00, adesso 21:06:10: mancano 50 s -> «prima tranche fra 50 s (attesa dal gol)».
- Seconda puntata abbinata alle 21:05:40, secondo gol alle 21:06:50: alle 21:07:00 i 120 s dal primo gol sono
  passati, ma sono solo 10 s dal secondo -> Mike aspetta fino alle 21:07:35.
- Copertura piena dopo la finestra scaduta (0-0): nessuna attesa, compra subito.

**Cosa vedi nell'app**
- «prima tranche fra N s (attesa dal gol)», «attendo per coprire».

**Se qualcosa va storto**
- Se il momento del gol e' sconosciuto la prima tranche non aspetta.
- Un secondo gol fa slittare la prima tranche di altri 45 s (Differenze 12 dell'inventario).

**Paper e live**: identico.

**Per il tecnico**: `attesa_prima_tranche` `engine.py:3228-3237`; attesa dopo gol `cover_timing` 1231-1234 e
`dopo_gol` 3327-3330 (`cover_forced` non la scavalca); ramo «attendo per coprire» 3360-3365. Parametri
`early_goal_cover_delay_s`, `cover_postgoal_delay_s`, `cover_wait_*`, `cover_good_price`. Inventario B schede
33, 35; Differenze 9, 12.

---

## 3. Quanto comprare

**Cosa fa**
- Mike calcola l'importo della punta Over 4,5 perche', con 5 o piu' gol, l'Over renda netto 1,2 volte il rischio
  Under, tolto quello che le coperture gia' abbinate rendono.
- **Formula**: importo pieno = (1,2 x rischio Under - gia' coperto) / ((quota Over - 1) x (1 - 0,05)).
  - La quota Over e' il MIGLIOR prezzo di punta di adesso (e' li' che l'ordine si abbina), non la quota limite.
  - Mai negativo.
- **Tutta o meta'**:
  - copertura normale (piena): compra il 100 %;
  - prima tranche dopo un gol precoce con seconda puntata abbinata: compra il 50 %;
  - seconda tranche: ricalcola il pieno sul prezzo di adesso, tolto il gia' coperto (cioe' compra il resto).
- **Arrotondamento**:
  - importi esatti accesi (serie): al centesimo, qualunque cifra (sotto i 2 euro in live Mike usa il
    «piazza e taglia»);
  - importi esatti spenti: minimo 2,00 euro, passo 0,50, per eccesso. Se il rialzo supera il 30 % Mike
    arrotonda per difetto; se anche cosi' supera il 30 %, aspetta. Con importi esatti spenti la divisione in
    meta' si fa solo se ogni meta' arriva da sola a 2,00 euro, altrimenti compra tutto in una volta.

**Quando**
- Nello stesso giro di «Serve coprire?», quando la risposta e' «compra».

**Numeri**
- Fattore 1,2 (regolabile 1-3). Commissione 5 %.
- Frazione della prima tranche 50 % (regolabile 0-100; 0 o 100 = tutto in una volta).
- Importo minimo: 0,01 euro (importi esatti) o 2,00 euro (importi esatti spenti).
- Tetto di rialzo 30 %.

**Esempio con le cifre** (copertura piena, passo per passo)
1. Posizione: punta Under 3,5 10,00 euro a 1,50. Rischio Under = 10,00 euro.
2. Gia' coperto = 0,00 euro.
3. Obiettivo con 5+ gol: 1,2 x 10,00 = 12,00 euro netti dall'Over.
4. Miglior punta Over 4,5 = 6,6. Guadagno netto per ogni euro puntato: (6,6 - 1) x 0,95 = 5,32 euro.
5. Importo = 12,00 / 5,32 = 2,2556 -> 2,26 euro.
6. Esiti a fine partita:
   - 0-3 gol: Under +5,00 lordi (+4,75 netti), Over -2,26 -> +2,74 lordi, +2,49 netti;
   - 4 gol: Under -10,00, Over -2,26 -> -12,26 euro;
   - 5+ gol: Over +2,26 x 5,6 x 0,95 = +12,02, Under -10,00 -> +2,02 euro.

**Esempio con le cifre** (due tranche dopo un gol precoce)
1. Posizione: 10,00 a 1,50 + 5,00 a 1,95 = 15,00 euro. Rischio Under = 15,00 euro.
2. 120 s dopo il gol, Over 4,5 a 8,0: pieno = 18,00 / (7,0 x 0,95) = 18,00 / 6,65 = 2,707 euro; meta' = 1,35 euro.
3. Gia' coperto dopo la prima tranche: 1,35 x 7,0 x 0,95 = 8,98 euro.
4. 180 s dopo, Over sceso a 5,0: resto = (18,00 - 8,98) / (4,0 x 0,95) = 9,02 / 3,80 = 2,37 euro.
5. Esiti: 5+ gol -> Over (1,35 x 7,0 + 2,37 x 4,0) x 0,95 = +17,98, Under -15,00 -> +2,98; 0-3 gol -> Under
   +9,75 lordi (+9,26 netti), Over -3,72 -> +6,03 lordi, +5,54 netti; 4 gol -> -18,72 euro.

**Cosa vedi nell'app**
- Nel diario la voce «copertura» con importo calcolato, importo piazzato, quota, rischio, gia' coperto, fase e
  frazione.
- «copertura Over 4.5 in una volta (la tranche sarebbe sotto il minimo)» se la divisione e' stata annullata.
- «copertura: overshoot X% oltre il tetto 30%» se il rialzo e' troppo.

**Se qualcosa va storto**
- Importo sotto 0,01 euro: «copertura gia' sufficiente», nessun ordine (riquadro 8).

**Paper e live**: identico nel bot.

**Per il tecnico**: `cover_residual` `engine.py:426-435`; `under_liability` 459-465; `cover_matched_value`
446-456; `frazione_copertura` 3240-3270; `cover_legal_size` 486-506; `legalize_back_size` 468;
`_decide_uncovered` 3299-3339 (calcoli), 3369-3382 (arrotondamento e tetto di rialzo). Parametri
`cover_profit_factor`, `commission_pct`, `early_goal_cover_pct`, `exact_sizes`, `cover_rounding`,
`cover_max_overshoot_pct`. Inventario B schede 34, 35, 36.

---

## 4. Punta Over 4,5

**Cosa fa**
- Ultimi controlli prima dell'ordine:
  1. Lo spazio sotto il tetto di esposizione per partita e' sotto 0,01 euro? Si' -> «Niente copertura»
     («copertura saltata: cap liability partita»). Se l'importo supera lo spazio, viene tagliato allo spazio.
  2. La liquidita' al miglior prezzo Over e' minore dell'importo? Si' -> aspetta («copertura: liquidita X < Y»).
  3. L'importo e' sotto 0,01 euro? Si' -> aspetta («copertura: size non piazzabile»).
- Poi Mike punta l'Over 4,5 con quota LIMITE 2 tick sotto il miglior prezzo (se il limite non si puo' calcolare,
  al miglior prezzo). Il limite serve a sopravvivere al ritardo di piazzamento in gioco: l'ordine si abbina
  comunque al miglior prezzo disponibile, mai sotto il limite.
- Passa alla fase «copertura in coda» («Sul book»).
- Prima di mandare l'ordine passano i freni (riquadro 10). Il servizio poi controlla ancora: mercato aperto,
  prezzi vivi, prezzo ancora disponibile (vedi «Se qualcosa va storto»).

**Quando**
- Nello stesso giro in cui «Quanto comprare» ha dato un importo.

**Numeri**
- 2 tick sotto il miglior prezzo (regolabile 0-6). Scala: 0,05 fra 3 e 4; 0,10 fra 4 e 6; 0,20 fra 6 e 10.
- Tetto di esposizione per partita: 0 = spento (serie).

**Esempio con le cifre**
- Importo 2,26 euro, miglior punta Over 6,6 con 40,00 euro disponibili: ordine punta 2,26 euro a 6,2 (limite).
  Se il mercato e' ancora a 6,6 si abbina a 6,6; se nel ritardo scende a 6,4 si abbina a 6,4; sotto 6,2 no.
- Prima tranche 1,35 euro con Over a 8,0: limite 7,6.
- Seconda tranche 2,37 euro con Over a 5,0: limite 4,8.

**Cosa vedi nell'app**
- Nella scheda Trade la punta Over 4,5. Motivo: «copertura Over 4.5», «... prima tranche», «... seconda tranche
  (residuo)», «... in una volta (la tranche sarebbe sotto il minimo)».

**Se qualcosa va storto**
- Tipo d'ordine (area ordini): la copertura parte «tutto o niente» e cade alla sospensione; si abbina subito o
  viene annullata. Sotto il minimo di Betfair, in live, «piazza e taglia».
- **Prezzi non vivi** (feed fermo): nessuna copertura parte (FATTO NUOVO c, vedi «Punti da decidere» n. 4).
- **Prezzo sparito**: se il miglior prezzo e' sceso sotto il limite, niente ordine; Mike ricorda questa richiesta
  e non la ripete identica.
- **Mercato non aperto** al momento dell'invio: niente ordine (non conta come rifiuto).
- **Flusso prezzi interrotto** (prezzi letti dal ripiego): la copertura parte lo stesso (conta come protezione).
- In live i freni di sicurezza delle aperture (freno d'emergenza, modo ordini della Control Room) bloccano anche
  la copertura, e quel rifiuto viene contato (riquadro 10).

**Paper e live**: identico nel bot. In paper l'ordine lo esegue il simulatore (runner); in live va a Betfair.

**Per il tecnico**: `engine.py:3383-3412` (tetto 3383-3388; liquidita' 3389-3393; importo 3394-3397; ordine
3398-3412, ruolo `over_cover`, `MARKET_OU45`, `SEL_OVER`); `cover_place_price` 1687. Servizio
`execute_place` `service.py:618-943` (mercato 691-699, ripiego REST 700-708, feed stantio 709-717, prezzo
disponibile 718-740). Inventario B scheda 36; C schede 16, 19, 22, 24.

---

## 5. Sul book

**Cosa fa**
- Mike segue la punta di copertura. Domande in ordine:
  1. La gamba di copertura non c'e'? -> torna a «Serve coprire?» («gamba copertura assente»).
  2. Non e' piu' sul book e non si e' abbinata per intero (annullata con 0 o con una parte abbinata)? -> torna a
     «Serve coprire?», tentativi +1; la nuova copertura si calcola sul gia' coperto reale.
  3. Abbinata per intero?
     - se era la prima tranche -> segna l'ora, passa in attesa della seconda tranche (riquadro 7);
     - altrimenti -> «Posizione coperta» (riquadro 6).
  4. E' sul book da almeno 10 secondi e i tentativi sono meno di 20? -> «Riprezzo» (riquadro 11).
  5. Altrimenti -> aspetta («attesa fill copertura»).

**Quando**
- A ogni giro nella fase «copertura in coda».

**Numeri**
- 10 secondi prima del riprezzo (regolabile 1-600); in pratica almeno 15 secondi per il ritmo minimo (riquadro 10).
- Massimo 20 tentativi (contatore condiviso, vedi «Punti da decidere» n. 6).

**Esempio con le cifre**
- Punta 2,26 a 6,2 abbinata subito a 6,6 -> «copertura abbinata».
- Punta 2,26 annullata dopo aver abbinato 1,00 euro a 6,6: gia' coperto 1,00 x 5,6 x 0,95 = 5,32; al giro dopo
  il resto e' (12,00 - 5,32) / 5,32 = 1,26 euro (se l'Over e' ancora a 6,6).

**Cosa vedi nell'app**
- «copertura abbinata», «prima tranche di copertura abbinata», «copertura non completata: ridimensiono sulla
  copertura reale gia' abbinata», «attesa fill copertura».
- Se il mercato Over 4,5 si sospende mentre la copertura e' in corso: una riga «mercato sospeso» e, alla
  riapertura, «mercato riaperto: la copertura riprende».

**Se qualcosa va storto**
- Poiche' la copertura parte «tutto o niente» (area ordini), di solito o e' abbinata subito o e' annullata: la
  strada normale e' la 2 (torna a «Serve coprire?»), non il riprezzo.
- Esito ignoto (nessuna risposta chiara da Betfair): la gamba va in riconciliazione, non si conta come rifiuto, e
  intanto nessuna apertura parte.

**Paper e live**: identico nel bot. In paper il servizio aspetta la risposta del simulatore fino a 15 s.

**Per il tecnico**: `_decide_cover_pending` `engine.py:3425-3498` (1: 3427-3428; 2: 3429-3445; 3: 3446-3456;
4: 3457-3497; 5: 3498). Stato `LIVE_COVER_PENDING`, `cover_stage`, `cover_stage1_at`. Sorveglianza del mercato
4,5: `service.py:2965-3009`. Inventario B scheda 38; C schede 21, 24, 55.

---

## 6. Posizione coperta

**Cosa fa**
- La copertura e' fatta (o Mike ha deciso di non farla). Da qui valgono le uscite globali: cash out, perdita
  tollerata, tetto di perdita della partita (schema 05).
- Se si e' in attesa della seconda tranche, dopo le uscite globali Mike guarda il riquadro 7.

**Quando**
- Dal giro in cui la copertura si abbina per intero, o in cui Mike rinuncia (riquadro 8).

**Numeri**
- Nessuno qui (vedi schema 05).

**Esempio con le cifre**
- Under 10,00 a 1,50 + Over 2,26 a 6,6: capitale investito 12,26 euro. Cash out a profitto quando il netto
  bloccabile arriva al 5 % di 12,26 = 0,61 euro (schema 05).

**Cosa vedi nell'app**
- Fase «coperta».

**Se qualcosa va storto**
- Vedi schema 05.

**Paper e live**: identico.

**Per il tecnico**: stato `LIVE_COVERED`, `_decide_covered` `engine.py:3511-3603`. Inventario B schede 40-44.

---

## 7. Seconda tranche

**Cosa fa**
- Solo dopo un gol precoce con copertura in due meta'. Se nessuna uscita globale e' scattata, Mike aspetta 180
  secondi dall'abbinamento della prima tranche, poi torna a «Serve coprire?» per comprare il resto al prezzo di
  quel momento.
- Il senso: senza altri gol la quota Over 4,5 sale, e la seconda meta' costa meno.
- Se l'ora della prima tranche manca (per esempio dopo un riavvio), compra subito il resto.

**Quando**
- A ogni giro nella fase «coperta», con la copertura in attesa della seconda tranche, dopo i controlli delle
  uscite globali.

**Numeri**
- 180 secondi dalla prima tranche (regolabile 0-900).

**Esempio con le cifre**
- Prima tranche 1,35 euro a 8,0 abbinata alle 21:07:00. Alle 21:10:00 Over a 5,0 -> seconda tranche 2,37 euro
  (limite 4,8). Prima delle 21:10:00: «tengo».

**Cosa vedi nell'app**
- «seconda tranche: completo la copertura», oppure «tengo»; nel diario la voce della tranche.

**Se qualcosa va storto**
- Se nel frattempo scatta un cash out o un'uscita (schema 05), la seconda tranche non si compra.
- Se arriva un gol nel frattempo, la seconda tranche aspetta 45 s dopo quel gol (riquadro 2); con 3 o piu' gol in
  partita non si compra (riquadro 8).

**Paper e live**: identico.

**Per il tecnico**: `_decide_covered` `engine.py:3593-3603` (`cover_stage` 2 -> 3, `early_goal_cover2_delay_s`,
`cover_forced`). Inventario B scheda 44.

---

## 8. Niente copertura

**Cosa fa**
- Mike rinuncia alla copertura e passa a «Posizione coperta» senza aver comprato niente (o senza comprare altro).
  Casi:
  1. copertura spenta nelle impostazioni («copertura disabilitata»);
  2. 3 o piu' gol in partita («copertura saltata: troppi gol»);
  3. rischio Under zero o meno («nessuna liability Under da coprire»);
  4. importo sotto 0,01 euro («copertura gia' sufficiente»);
  5. tetto di esposizione per partita raggiunto («copertura saltata: cap liability partita»).

**Quando**
- Nel giro in cui «Serve coprire?» o «Punta Over 4,5» trovano uno di questi casi.

**Numeri**
- Massimo 2 gol per coprire. Soglia 0,01 euro. Tetto per partita 0 = spento.

**Esempio con le cifre**
- 2-1 al 25' con Under 3,5 da 10,00 a 1,50: niente copertura. Se finisce 2-1: +5,00 lordi. Se finisce 3-1 o 2-2
  o piu': -10,00 euro, senza protezione anche con 5+ gol.

**Cosa vedi nell'app**
- I motivi fra parentesi sopra.

**Se qualcosa va storto**
- E' una scelta della strategia, non un errore: con 3 o piu' gol la posizione resta senza copertura (vedi «Punti
  da decidere» n. 7).

**Paper e live**: identico.

**Per il tecnico**: `engine.py:3284-3286`, `3340-3342`, `3343-3345`, `3366-3368`, `3383-3386`; tutti mettono
`cover_skipped` = vero, `cover_stage` 0. Inventario B schede 35, 36.

---

## 9. Aspetta

**Cosa fa**
- Mike resta nella fase «da coprire» senza piazzare, e riprova al giro dopo, se:
  1. il mercato Over/Under 4,5 e' sospeso, chiuso o sconosciuto;
  2. la liquidita' al miglior prezzo e' minore dell'importo;
  3. l'importo dopo gli arrotondamenti non e' piazzabile;
  4. con importi esatti spenti, il rialzo al minimo supera il 30 %.
- Con la copertura gia' sul book e il mercato sospeso, Mike NON fa il riprezzo (ritirarla lascerebbe la
  posizione scoperta per niente).

**Quando**
- A ogni giro nella fase «da coprire» o «copertura in coda».

**Numeri**
- Nessuna soglia di tempo: aspetta finche' il motivo sparisce.

**Esempio con le cifre**
- Gol al 30': il mercato 4,5 si sospende per 40 s. Mike scrive «copertura: mercato Over 4.5 sospeso, si aspetta la
  riapertura»; alla riapertura aspetta ancora i 45 s dopo il gol (riquadro 2), poi copre.
- Importo 2,26, liquidita' a 6,6 solo 1,80 euro: «copertura: liquidita 1.80 < 2.26», riprova al giro dopo.

**Cosa vedi nell'app**
- I motivi sopra; una riga «mercato sospeso» e una «mercato riaperto» dal servizio (una per cambio di stato).

**Se qualcosa va storto**
- Con poca liquidita' Mike non compra una parte: aspetta che ci sia l'importo intero (non e' scritto un limite di
  tempo).

**Paper e live**: identico.

**Per il tecnico**: `engine.py:3353-3359` (mercato), `3378-3382` (rialzo), `3389-3397` (liquidita', importo),
`3465-3468` (niente riprezzo a mercato fermo); `service.py:2965-3009` (`_sorveglia_mercato_copertura`).
Inventario B schede 35, 36, 38; C scheda 55.

---

## 10. Freno rifiuti

**Cosa fa**
- Due freni valgono per OGNI copertura, sia la prima volta sia il riprezzo:
  1. **Bloccata**: se il mercato rifiuta la copertura 3 volte con lo stesso codice d'errore, la copertura si
     ferma. Non si ritenta piu' finche' tu non premi «Riprendi», oppure finche' arriva un rifiuto con un codice
     DIVERSO (che fa ripartire il conteggio da 1).
  2. **Ritmo minimo**: fra due tentativi di copertura devono passare almeno 15 secondi. L'orologio parte quando
     Mike manda l'ordine, non quando arriva la risposta.
- Quando un freno scatta, Mike toglie sia la nuova punta sia l'eventuale ritiro della vecchia (ritirare senza poter
  ripiazzare lascerebbe la posizione piu' scoperta), e non consuma tentativi.
- C'e' una seconda barriera nel servizio: con il freno scattato l'ordine di copertura non parte comunque.
- Uscite, chiusure e cash out non passano da questo freno.
- **Mai sovracopertura**: se c'e' gia' una copertura sul book (o a esito ignoto), una nuova copertura aspetta il
  giro dopo.

**Quando**
- A ogni giro in cui una decisione contiene una punta di copertura.

**Numeri**
- Massimo 3 rifiuti con lo stesso codice (regolabile 1-20).
- Minimo 15 secondi fra due tentativi (regolabile 1-300).

**Esempio con le cifre**
- 21:04:00 copertura 2,26 a 6,2 rifiutata con codice A (1/3). 21:04:15 ritenta: rifiutata A (2/3). 21:04:30:
  rifiutata A (3/3) -> copertura FERMATA. La posizione Under da 10,00 resta scoperta: con 5+ gol perdi 10,00 euro
  invece di guadagnare +2,02. Si sblocca con «Riprendi».
- Rifiuti A, A, B: il conteggio riparte da 1 con B, nessun blocco.

**Cosa vedi nell'app**
- «copertura: ritento fra N s (ritmo minimo fra due tentativi)».
- «copertura FERMATA dal freno: 3 rifiuti con lo stesso codice (...) - serve l'utente».
- Nel diario: rifiuto con codice «x/3» e poi un errore critico «copertura bloccata».

**Se qualcosa va storto**
- **FATTO NUOVO (b)**, verificato da me nel codice del servizio: un rifiuto dovuto a un FRENO (freno d'emergenza,
  modo ordini della Control Room, freni non leggibili, freno del paper) viene contato fra i rifiuti della
  copertura come se l'avesse detto il mercato. Dopo 3 con lo stesso motivo la copertura resta bloccata anche
  quando il freno viene tolto, finche' non premi «Riprendi».
- In paper il simulatore non da' un codice d'errore: si conta sul tipo di esito («annullato», «scaduto»,
  «rifiutato»). Se gli esiti si alternano, il conteggio riparte ogni volta e il blocco puo' non scattare mai
  (area ordini, Cose strane 24; non verificato da me).
- Un esito ignoto NON si conta: li' comanda la riconciliazione.

**Paper e live**: stessa regola. Diverso il codice contato (vedi sopra). In live la copertura e' frenata dal freno
d'emergenza e dal modo ordini perche' per il servizio NON e' una chiusura.

**Per il tecnico**: `_freno_copertura` `engine.py:2023-2074` (chiamato in `decide` 2208 prima di
`_una_sola_lay` e `_mai_sovracopertura` 2212); `registra_rifiuto_copertura` 1595-1615; `copertura_bloccata`
1618; `attesa_ritento_copertura` 1638-1650; `sblocca_copertura` 1653 (chiamato da «Riprendi»,
`service.py:3154-3157`); `segna_tentativo_copertura` `service.py:817-822`; seconda barriera `service.py:677-690`;
conteggio `_esito_rifiuto_mercato` 946-1004, chiamato nel ramo rifiuto 927-942 PRIMA di `_ferma_aperture`.
Parametri `cover_rifiuti_max` (3), `cover_retry_min_s` (15) `config.py:226-227`. Stato `LIVE_COVER_BLOCKED`.
Inventario B premessa punto 2; C schede 18, 25, 56, Cose strane 1, 2, 24.

---

## 11. Riprezzo

**Cosa fa**
- Se la punta di copertura resta sul book senza abbinarsi per almeno 10 secondi (e i tentativi sono meno di 20):
  1. mercato 4,5 non aperto -> nessun riprezzo, aspetta;
  2. ricalcola il resto da comprare sul miglior prezzo di ADESSO e sul gia' coperto reale (in prima tranche,
     sempre la stessa meta');
  3. se il resto e' sotto 0,01 euro -> ritira la punta, «Posizione coperta» («copertura sufficiente»);
  4. altrimenti ritira la punta vecchia e manda la nuova 2 tick sotto il nuovo miglior prezzo; tentativi +1.
     La nuova parte al giro dopo, quando la vecchia risulta ritirata (mai due coperture insieme).

**Quando**
- Dal riquadro «Sul book», dopo almeno 10 secondi, e comunque non prima di 15 secondi dall'ultimo tentativo
  (riquadro 10).

**Numeri**
- 10 secondi (regolabile 1-600); ritmo minimo 15 secondi; 20 tentativi; 2 tick sotto.

**Esempio con le cifre**
- Punta 2,26 a 6,2 non abbinata in 15 s; l'Over e' sceso a 6,0. Resto = 12,00 / (5,0 x 0,95) = 2,53 euro, limite
  5,8 (2 tick da 0,10 sotto 6,0). Mike ritira la 2,26 e manda 2,53 a 5,8.

**Cosa vedi nell'app**
- «copertura: riprezzo», «copertura sufficiente», «copertura: mercato Over 4.5 sospeso, nessun riprezzo».

**Se qualcosa va storto**
- Con la copertura «tutto o niente» (area ordini) il riprezzo scatta raramente: di solito la punta e' gia'
  annullata e si passa dal riquadro 5, punto 2.
- Dopo 20 tentativi il riprezzo si ferma e resta «attesa fill copertura».

**Paper e live**: identico.

**Per il tecnico**: `_decide_cover_pending` `engine.py:3457-3497`; guardia `_mai_sovracopertura` (area A,
`engine.py:1972`). Parametri `close_retry_s`, `close_max_attempts`, `cover_place_at_ticks`. Inventario B
scheda 38.

---

## Frecce

Nello schema:
- Serve coprire? -> Attesa dal gol: posizione Under > 0, copertura accesa, massimo 2 gol, rischio Under > 0,
  mercato 4,5 aperto.
- Attesa dal gol -> Quanto comprare: passati 120 s dal gol (solo prima tranche) e 45 s dall'ultimo gol, quota Over
  presente.
- Quanto comprare -> Punta Over 4,5: importo >= 0,01 euro (importi esatti) e rialzo entro il 30 % (importi esatti
  spenti).
- Punta Over 4,5 -> Sul book: spazio sotto il tetto, liquidita' >= importo, freni non scattati; ordine inviato.
- Sul book -> Posizione coperta: copertura abbinata per intero (non prima tranche).
- Serve coprire? -> Niente copertura: copertura spenta, 3+ gol, rischio Under <= 0, importo < 0,01, tetto per
  partita raggiunto.
- Attesa dal gol -> Aspetta: mercato Over/Under 4,5 sospeso, chiuso o sconosciuto (nel codice questa domanda viene
  prima dell'attesa dei 45 s).
- Punta Over 4,5 -> Freno rifiuti: 3 rifiuti con lo stesso codice, oppure meno di 15 s dall'ultimo tentativo.
- Sul book -> Riprezzo: punta sul book da >= 10 s, tentativi < 20, mercato aperto.
- Riprezzo -> Punta Over 4,5: resto >= 0,01 euro; nuova punta al giro dopo, 2 tick sotto il nuovo miglior prezzo.
- Posizione coperta -> Seconda tranche: prima tranche abbinata (fase 2).
- Seconda tranche -> Quanto comprare: passati 180 s dalla prima tranche (o ora sconosciuta) e nessuna uscita
  globale scattata; Mike torna nella fase «da coprire» con la fase «seconda tranche».

Fuori dallo schema (solo nelle schede):
- Sul book -> Serve coprire?: gamba assente, oppure annullata senza abbinamento pieno (tentativi +1).
- Sul book -> Seconda tranche: prima tranche abbinata per intero (passa da «Posizione coperta»).
- Riprezzo -> Posizione coperta: resto sotto 0,01 euro (ritira la punta).
- Freno rifiuti -> Serve coprire?: «Riprendi» premuto, codice d'errore diverso, o passati 15 s.
- Serve coprire? -> senza posizione (schema 03): posizione Under = 0.
- Aspetta -> Serve coprire?: al giro dopo, quando il motivo e' sparito.

---

## Punti da decidere

1. **Nessuna attesa intelligente nel flusso normale** (Costituzione §3 Fase 3): tutte le strade verso la
   copertura arrivano «ordinate», e con la copertura ordinata resta solo l'attesa di 45 s dopo un gol
   (`engine.py:3329-3330`). Le soglie dell'attesa intelligente (10 minuti, 6 %, 16 %, 7,0, 8 %) oggi non
   cambiano niente.
2. **Esito ignoto blocca la copertura** (mia deduzione dal codice, da confermare col replay): la copertura e' fra
   le «aperture» (`engine.py:50`), e con un ordine a esito ignoto sulla partita tutte le aperture vengono tolte
   (`engine.py:2189-2191`). Unito al FATTO NUOVO (a) dello schema 03 (in live, dopo una sospensione, la banca
   d'uscita sparita dagli ordini correnti e' sempre «esito ignoto»), una posizione puo' restare scoperta fino
   alla fine della riconciliazione. Da decidere se la copertura debba restare permessa.
3. **FATTO NUOVO (b) - i freni contano come rifiuti** (verificato da me: `service.py:927-942`, il conteggio avviene
   prima di `_ferma_aperture`): un rifiuto da freno di sicurezza entra nei 3 rifiuti della copertura; dopo 3 la
   copertura resta bloccata anche a freno tolto, fino a «Riprendi». Il commento del codice dice che si dovrebbero
   contare solo le risposte del mercato.
4. **FATTO NUOVO (c) - prezzi non vivi = nessuna copertura** (verificato da me: `service.py:709-717`, vale per
   ogni ordine, paper e live). La Costituzione §5 diceva «chiusure permesse»; la copertura non e' una chiusura
   ma protegge: con il feed fermo la posizione resta scoperta. Al contrario, col flusso interrotto e prezzi dal
   ripiego la copertura parte.
5. **La copertura frenata come un'apertura** (area ordini, Cose strane 2): in live il freno d'emergenza e il modo
   ordini della Control Room bloccano la copertura; il runner giu' in paper ferma le aperture comprese le
   coperture; ma col ripiego dei prezzi la copertura e' trattata come protezione. Due regole diverse per la
   stessa puntata.
6. **Contatore dei tentativi condiviso** con riprezzi pre-partita e seconda puntata: si azzera quando la copertura
   si abbina, ma la copertura puo' partire con meno di 20 tentativi disponibili.
7. **3 o piu' gol = nessuna copertura**: e' la regola di serie (massimo 2 gol). Con 3 gol la posizione Under 3,5
   perde al prossimo gol senza alcuna protezione.
8. **Tipo d'ordine della copertura**: la strategia prevede che resti sul book e venga riprezzata dopo 10 s;
   secondo l'area ordini parte «tutto o niente» (FOK), quindi si abbina subito o viene annullata. Verificato da
   me solo per il canale paper (`Betfair/safe_strategy/execution.py:531-533`); il live e' da confermare.
9. **Freno in paper**: il conteggio usa il tipo di esito del simulatore; esiti alternati azzerano il conteggio
   (area ordini, Cose strane 24, non verificato da me).
10. **Costituzione §15.2 riga B** (copertura «in coda» subito dopo la finestra scaduta): il codice passa prima
    dalla fase «da coprire» e la punta parte al giro dopo (Differenze 8 dell'inventario).
