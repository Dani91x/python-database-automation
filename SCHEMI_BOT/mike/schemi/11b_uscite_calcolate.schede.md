# Schema 11b - I conti di Mike: le uscite calcolate e il giro di decisione

Schema: `11b_uscite_calcolate.html` (tipo workflow). Viene dopo `11a_posizione_e_profitto.html`.

**Schede dell'inventario A usate in questo file**: 49, 50, 51, 52, 53, 54, 55, 56, 57, 79, 82, 83, 84,
85, 86, 87, 96, 97, 108 (piu' richiami alle schede 36, 38, 39, 81 gia' spiegate in 11a).
Le schede rimandate agli schemi 06 e 08 sono elencate in fondo.

**Come si legge lo schema.** In alto il giro di decisione (da sinistra a destra). Se l'Under non e'
ancora coperto si va alla corsia "Copertura Over 4,5". Se e' coperto si scende nella corsia delle
uscite: Mike fa quattro domande in fila, da sinistra a destra; al primo "si'" scende a "Chiude
tutto"; se tutte rispondono "no" arriva a "Tiene". Ogni decisione passa poi dalle guardie (schema 08)
e, se e' un'uscita, dal cancello delle uscite (schema 06).
Colori: arancio = decisione si'/no; ambra = attesa; verde = azione; rosa = perdita o blocco; grigio =
rimando a un altro schema.

**L'esempio unico** (lo stesso di 11a): Under 3,5 10,00 euro a 1,50 + copertura Over 4,5 2,26 euro a
6,60. Capitale investito (la "base" delle percentuali) = 10,00 + 2,26 = **12,26 euro**.
Risultato per gol finali: 0-3 gol +2,49; 4 gol -12,26; 5+ gol +2,02. Commissione 5%.

---

## 1. Ogni giro (arancio, decisione)

**Cosa fa.** A ogni giro Mike decide cosa fare su una partita, in quest'ordine:
1. La partita e' in una fase finale (regolata, errore, saltata)? Si' -> non fa nulla.
2. Se il mercato NON e' chiuso e non si sta regolando:
   - L'utente ha chiuso la posizione FUORI dall'app? Si' -> Mike non fa piu' nulla su questa partita
     (ne' aperture ne' chiusure); la fase resta, e al mercato chiuso si regola il vero.
   - C'e' una chiusura manuale in corso (pulsante cash out dalla pagina)? Si' -> segue la procedura
     qui sotto e basta.
   - C'e' il "non rientrare" (dopo un cash out manuale)? Si' -> spegne ingressi pre-match,
     re-ingresso e ultimo ingresso.
3. Chiede la decisione alla regola della fase (riquadro 2).
4. C'e' un ordine a esito ignoto? Si' -> toglie dalla decisione tutti gli ordini che aggiungono
   rischio. Altrimenti: aperture ferme per una causa che non e' il mercato (modo ordini non attivo,
   interruttore d'emergenza, simulatore paper giu')? Si' -> stessa cosa.
5. Passa la decisione alle guardie (freno della copertura, mai due bancate, mai sovracopertura:
   schema 08) e poi al cancello delle uscite (schema 06).

**La chiusura manuale in corso**, passo per passo:
1. Ci sono ordini vivi (esclusa la chiusura manuale)? Si' -> li ritira; fase invariata.
2. C'e' una chiusura manuale sul book? Si' -> se e' sul book da almeno 10 secondi e i tentativi
   sono meno di 20, la ritira e ripiazza il residuo (tentativo +1); altrimenti aspetta il fill.
3. Ci sono chiusure da fare? Si' -> le piazza (tentativi da zero).
4. Una selezione viva non ha quota? Si' -> aspetta.
5. Resta solo una selezione con esito gia' deciso dai gol? Si' -> fase piatta (in gioco) o
   osservazione (pre-match), SENZA archiviare le gambe: la paghera' il regolamento. Niente piu'
   rientri.
6. Altrimenti: completata. In gioco -> fase piatta, gambe archiviate, niente piu' rientri.
   Pre-match -> osservazione, ciclo +1, gambe archiviate, niente rientri finche' l'utente non preme
   "Riprendi".

**Quando.** A ogni giro del servizio; fra due decisioni passano almeno 0,5 secondi.

**Numeri.** Intervallo minimo fra due decisioni 500 millisecondi (pagina: da 100 a 5.000). Riprezzo
della chiusura manuale dopo 10 secondi (pagina: da 1 a 600). Tentativi massimi 20 (pagina: da 1 a 100).

**Esempio con le cifre.** Minuto 30, Under 10,00 a 1,50, green pre-match 10,14 a 1,48 ancora sul
book. L'utente preme "cash out".
- Giro 1: Mike ritira la bancata di green (nessun'altra azione).
- Giro 2: banca migliore dell'Under 1,40. Importo = 15,00 / 1,40 = 10,71 euro. Mike banca 10,71 a
  1,40.
- Se in 10 secondi non si abbina: la ritira e la ripiazza al prezzo nuovo (tentativo 1 di 20).
- Abbinata: se l'Under vince 5,00 - 10,71 x 0,40 = +0,72; se perde -10,00 + 10,71 = +0,71;
  netto circa +0,67. Fase piatta, gambe archiviate, niente piu' rientri.

**Cosa vedi nell'app.** "chiusura manuale: annullo gli ordini vivi / attendo il fill / riprezzo /
chiudo la posizione / completata"; attivita' "chiuso dall'utente"; "(ordine a esito ignoto: nessuna
apertura)".

**Se qualcosa va storto.** A 20 tentativi esauriti la chiusura manuale resta ferma in "attendo il
fill" e non riprezza piu' (vedi "Punti da decidere").

**Per il tecnico.** `engine.py:2164-2216` (`decide`), `2077-2161` (`_decide_flatten`), `1786-1812`
(`MANUAL_ROLE_MAP`, `force_flat_plan`, `force_flat_actions`); parametri `decide_min_interval_ms`
(letto in `service.py`), `close_retry_s`, `close_max_attempts`. Inventario A: schede 85, 86, 96, 97.
Paper e live: uguale; le "aperture ferme" le scrive il servizio (anche per "simulatore paper giu'").

---

## 2. Regola della fase (arancio, decisione)

**Cosa fa.** Sceglie la regola giusta secondo la fase della partita:
- **Mercato chiuso** (o gia' in regolamento):
  1. prima volta: fase "regolamento" e ritiro di tutti gli ordini vivi;
  2. c'e' un ordine a esito ignoto? Si' -> regolamento SOSPESO (allarme);
  3. manca il punteggio finale? Si' -> aspetta;
  4. altrimenti regola (conti del riquadro 11 di 11a) e chiude la partita.
- **Fasi pre-match** (osserva, ingresso sul book, posizione aperta, green in attesa, tiene, ultimo
  ingresso): regola pre-match (schema 02).
- **In gioco senza posizione**: se non ci sono mai state gambe -> chiusa subito a 0,00 "nessuna
  operazione"; altrimenti resta.
- **Una regola per ogni fase in gioco**: uscita al fischio, seconda puntata, Under scoperto,
  copertura sul book, coperti, chiusura, piatto, re-ingresso (tre fasi). Qui interessano "Under
  scoperto" (riquadro 3) e "coperti" (riquadri 4-8).
- **Fase sconosciuta**: errore e ritiro di tutti gli ordini.

**Quando.** A ogni giro, dopo i controlli del riquadro 1.

**Numeri.** Commissione = valore della pagina / 100 (5 -> 0,05).

**Esempio con le cifre.** Mercato chiuso, finale 2-0: giro 1 "mercato chiuso" (ritira gli ordini
vivi); giro 2 "regolato T=2", risultato +2,49.

**Cosa vedi nell'app.** "mercato chiuso", "regolamento sospeso: un ordine ha esito ignoto", "attesa
punteggio finale", "regolato T=3", "nessuna operazione".

**Se qualcosa va storto.** Ordine a esito ignoto a mercato chiuso: il regolamento aspetta, per non
dichiarare un risultato falso.

**Per il tecnico.** `engine.py:2435-2491` (`_dispatch`). Inventario A: scheda 108.
Paper e live: uguale.

---

## 3. Quando coprire (ambra, attesa)

**Cosa fa.** Con l'Under 3,5 scoperto, Mike decide se comprare la copertura Over 4,5 ADESSO,
ASPETTARE o SALTARLA. Le domande, in ordine; la prima che risponde decide:
1. I gol sono piu' di 2? Si' -> SALTA la copertura.
2. La regola e' "subito"? Si' -> COPRE.
3. C'e' almeno un gol? Si' -> se l'ultimo gol e' di meno di 45 secondi fa ASPETTA (la quota
   dell'Over si deve riassestare), altrimenti COPRE.
4. Il minuto manca? Si' -> COPRE. Il minuto e' 10 o piu'? Si' -> COPRE.
5. La regola e' "aspetta"? Si' -> ASPETTA.
6. Manca la probabilita' di gol nei prossimi 3 minuti o la probabilita' dei 4 gol? Si' -> COPRE.
7. Probabilita' di gol nei prossimi 3 minuti sopra 0,06? Si' -> COPRE.
8. Probabilita' che finisca con 4 gol sopra 0,16? Si' -> COPRE.
9. Quota Over 7,0 o piu'? Si' -> COPRE (la quota e' gia' buona).
10. Risparmio atteso aspettando sotto l'8%? Si' -> COPRE.
11. Altrimenti ASPETTA.
Una copertura ordinata dal percorso (finestra al fischio scaduta, gol precoce) salta l'attesa
"intelligente", ma rispetta i 45 secondi dopo un gol.
Dopo il "COPRE", prima di piazzare, Mike controlla: perdita dell'Under sopra zero; mercato Over 4,5
aperto (se sospeso, chiuso o sconosciuto aspetta); importo calcolato almeno 0,01 (se no "copertura
gia' sufficiente"); tetto di eccesso e tetto per partita (11a, riquadri 9 e 12); euro disponibili
alla quota almeno pari all'importo (se no aspetta). Il percorso completo della copertura e' nello
schema 04.

**Quando.** Nella fase "Under scoperto", a ogni giro.

**Numeri.** Gol massimi 2 (pagina: da 0 a 4). Regola "auto" (pagina: auto, subito, aspetta). Attesa
dopo un gol 45 secondi (pagina: da 0 a 300). Attesa massima fino al minuto 10 (pagina: da 0 a 45).
Probabilita' di gol in 3 minuti massima 0,06; probabilita' dei 4 gol massima 0,16. Quota buona 7,0.
Risparmio minimo 8%. Prima tranche dopo un gol precoce: 120 secondi dal gol, 50% dell'importo;
seconda tranche 180 secondi dopo (schema 04).

**Esempio con le cifre.**
- Minuto 7, 0-0, probabilita' di gol in 3 minuti 0,04, probabilita' dei 4 gol 0,12, Over a 6,60,
  risparmio atteso 10% -> ASPETTA.
- Stessa situazione con Over a 7,20 -> COPRE (7,20 e' almeno 7,0).
- Stessa situazione al minuto 10 -> COPRE.
- Gol al minuto 12, 20 secondi fa -> ASPETTA; 45 secondi dopo il gol -> COPRE 2,26 euro (11a,
  riquadro 10).
- 3 gol al minuto 20 -> SALTA la copertura.

**Cosa vedi nell'app.** "attendo per coprire", "copertura saltata: troppi gol", "copertura: mercato
Over 4.5 sospeso, si aspetta la riapertura", "copertura: liquidita 1.50 < 2.26".

**Se qualcosa va storto.** Con i gol mancanti Mike li conta come 0 e puo' ASPETTARE, anche se la
regola scritta dice "ogni dato mancante = si copre" (vedi "Punti da decidere").

**Per il tecnico.** `engine.py:1212-1251` (`cover_timing`); chiamata in `_decide_uncovered`
`3273-3412` (fuori area A). Parametri `cover_max_goals`, `cover_policy`, `cover_postgoal_delay_s`,
`cover_wait_max_min`, `cover_wait_hazard_max`, `cover_wait_p4_max`, `cover_good_price`,
`cover_wait_min_gain_pct`. Inventario A: scheda 57. Paper e live: uguale.

---

## 4. Soglia 5% (arancio, decisione)

**Cosa fa.** Con la copertura in piedi, Mike si chiede: "se chiudo ora" (11a, riquadro 6) vale
almeno il 5% della base? Si' -> chiude tutto con motivo "profitto".
La base di serie e' il capitale investito (Under + copertura). In alternativa si puo' scegliere solo
l'importo dell'Under. Base zero -> la risposta e' sempre no.
Prima di questa domanda, all'ingresso della fase "coperti":
- nessuna selezione ancora gestibile? -> fase piatta;
- "se chiudo ora" incompleto (manca una quota)? -> resta coperto, nessuna uscita;
- ordine di ultimo ingresso che resta in gioco non abbinato 120 secondi dopo il fischio? -> lo ritira
  (vale per tutte le decisioni di questa fase).

**Quando.** A ogni giro nella fase "coperti".

**Numeri.** Soglia 5% (pagina: da 0,5 a 50). Base "capitale investito" (pagina: capitale investito o
solo Under). Ritiro dell'ultimo ingresso 120 secondi dopo il fischio (pagina: da 0 a 900).

**Esempio con le cifre.**
- Base 12,26 x 5% = soglia **0,613 euro**.
- Minuto 60, 1 gol, "se chiudo ora" = +0,78 (11a, riquadro 6): 0,78 e' almeno 0,613 -> CHIUDE.
- "Se chiudo ora" = +0,44 -> no, si passa al cash out intelligente.
- Base "solo Under": 10,00 x 5% = 0,50.

**Cosa vedi nell'app.** "profit: 0.78 >= 5.0% di 12.26"; "prezzi incompleti".

**Se qualcosa va storto.** Una quota mancante blocca TUTTE le uscite di questa fase, compreso il
tetto di perdita (riquadro 7).

**Per il tecnico.** `engine.py:1004-1007` (`should_cashout`), `1676-1684` (`cashout_base`,
`_cashout_base`); chiamata in `_decide_covered` `3511-3530` (fuori area A); ritiro dell'ultimo
ingresso `3415-3422` (`_late_persist_cancel`). Parametri `cashout_profit_pct`, `cashout_base`,
`cancel_unmatched_after_ko_s`. Inventario A: schede 36, 49, 79. Paper e live: uguale.

---

## 5. Cash out intelligente (arancio, decisione)

**Cosa fa.** Chiude PRIMA della soglia del 5% quando tenere non vale il rischio, ma mai sotto il
profitto minimo del 2%. Le domande in ordine:
1. Il cash out intelligente e' acceso e la base e' sopra zero? No -> non chiude.
2. "Se chiudo ora" e' sotto il 2% della base? Si' -> non chiude.
3. I gol sono 3 o piu' ("punteggio caldo": il prossimo gol e' il quarto)? Si' -> CHIUDE.
4. Siamo "a un passo" dalla soglia (entro 2 punti percentuali sotto il 5%) E la fase e' calda
   (probabilita' di gol nei prossimi 3 minuti almeno 0,10, oppure pressione almeno 1,15)? Si' ->
   CHIUDE.
5. Ci sono le probabilita' del modello e quella di gol in 3 minuti? Si' -> Mike immagina due futuri:
   - "gol adesso": ogni quota viene moltiplicata per (probabilita' adesso / probabilita' dopo il
     gol); una selezione con probabilita' quasi zero va a quota 1000 (praticamente morta); le quote
     restano fra 1,01 e 1000;
   - "fra 5 minuti senza gol": stessa cosa con le probabilita' di quel momento.
   Calcola "se chiudo ora" nei due futuri. Probabilita' di un gol nei prossimi 5 minuti = 1 - (1 -
   probabilita' in 3 minuti) elevato a 5/3. Valore dell'attesa = probabilita' del gol x valore dopo
   il gol + (1 - probabilita' del gol) x valore fra 5 minuti.
   - A un passo dalla soglia: CHIUDE se il valore dell'attesa e' sotto il valore di adesso.
   - Lontano dalla soglia: CHIUDE se il valore dell'attesa e' sotto il valore di adesso meno l'1%
     della base.
6. Altrimenti non chiude.

**Quando.** Nella fase "coperti", se la soglia del 5% non e' raggiunta.

**Numeri.** Acceso (pagina: si'/no). Profitto minimo 2%; "a un passo" 2%; punteggio caldo 3 gol;
probabilita' di gol in 3 minuti "calda" 0,10; pressione "calda" 1,15 (neutra 1,00); margine lontano
dalla soglia 1%; orizzonte 5 minuti (e' lo stesso parametro dell'attesa della copertura). Una
probabilita' vale solo se e' un numero vero fra 0 (escluso) e 1.

**Esempio con le cifre.** Base 12,26:
- Profitto minimo 12,26 x 2% = 0,245. Soglia 0,613. "A un passo" da 0,613 - 0,245 = 0,368.
- "Se chiudo ora" +0,44, 1 gol, probabilita' di gol in 3 minuti 0,11: 0,44 e' fra 0,368 e 0,613, fase
  calda -> **CHIUDE** ("fase calda a un passo dalla soglia").
- Stessa situazione con probabilita' 0,06 e pressione 1,00: non calda. Probabilita' di gol in 5
  minuti = 1 - 0,94 elevato a 5/3 = 0,098. Il modello dice: dopo un gol "se chiudo" varrebbe -3,00;
  fra 5 minuti senza gol +0,70. Valore dell'attesa = 0,098 x (-3,00) + 0,902 x 0,70 = -0,294 + 0,631
  = **0,34**. 0,34 e' sotto 0,44 e siamo a un passo -> **CHIUDE** ("aspettare vale 0.34 < 0.44").
- Proiezione di una quota: banca Under 3,5 a 1,30, probabilita' adesso 0,77, dopo un gol 0,55 ->
  1,30 x 0,77 / 0,55 = 1,30 x 1,4 = **1,82**.
- 3 gol e "se chiudo ora" +0,30 (sopra 0,245) -> **CHIUDE** ("punteggio caldo (3 gol)").

**Cosa vedi nell'app.** "profit smart: 0.44 (fase calda (hazard/pressione) a un passo dalla
soglia)", "(punteggio caldo ...)", "(aspettare vale ...)", "(attesa a valore atteso ...)".

**Se qualcosa va storto.** Probabilita' rotta o mancante: niente futuri immaginati, si salta il
punto 5. Gol mancanti contati come 0: il punto 3 non scatta (vedi "Punti da decidere").

**Per il tecnico.** `engine.py:1075-1132` (`smart_cashout`), `1037-1072` (`projected_books`),
`1018-1034` (`_PROB_KEY`, `_DEAD_PRICE` 1000, `_prob_utilizzabile`); chiamata a `3531-3539`.
Parametri `cashout_smart_enabled`, `cashout_smart_min_pct`, `cashout_smart_tolerance_pct`,
`cashout_smart_goals_hot`, `cashout_smart_hazard_hot`, `cashout_smart_pressure_hot`,
`cashout_smart_ev_margin_pct`, `cover_wait_step_min`. Inventario A: schede 51, 52, 53.
Paper e live: uguale.

---

## 6. Perdita a modello (arancio, decisione)

**Cosa fa.** Decide se chiudere IN PERDITA. Vale solo in due finestre:
- all'intervallo (se la regola dell'intervallo e' accesa);
- nel secondo tempo dal minuto 46 al minuto 85 (se la regola del secondo tempo e' accesa).
E solo con 3 o 4 gol segnati.
Il confronto (modo "a modello", di serie):
1. Mike prende la distribuzione dei gol finali: media fra modello ed esperienza storica; se mancano
   entrambe usa quella del mercato; se manca tutto, "non so".
2. Probabilita' dei 4 gol prudente: se quella del mercato e' piu' alta, si alza a quella e le altre
   si riducono in proporzione.
3. Valore di tenere = somma, per ogni numero di gol, di probabilita' x risultato (11a, riquadro 7,
   solo gambe non archiviate).
4. Premio al rischio = 10% x probabilita' dei 4 gol x base.
5. CHIUDE se "se chiudo ora" e' almeno (valore di tenere - premio). Altrimenti tiene.
6. Tetto (spento di serie): se acceso e la perdita supera quella % della base, tiene comunque.
Se il modello dice "non so" (o il modo scelto e' "regola fissa"), Mike usa la **regola fissa**: chiude
se "se chiudo ora" non e' peggio di -25% della base (o e' in utile), sempre con 3-4 gol.
Se il modello dice "tieni", la regola fissa non viene consultata.

**Quando.** Nella fase "coperti", dopo la soglia e il cash out intelligente.

**Numeri.** Modo "a modello" (pagina: modello o fissa). Premio 10% (pagina: da 0 a 300). Probabilita'
dei 4 gol prudente accesa. Tetto 0% = spento (pagina: da 0 a 100). Gol da 3 a 4 (pagina: da 0 a 8;
valgono per intervallo e secondo tempo). Regola fissa: 25% all'intervallo e 25% nel secondo tempo
(pagina: da 0 a 100). Secondo tempo dal minuto 46 al 85. Casi minimi della tabella storica 200 (letto
dal servizio).

**Esempio con le cifre.** Minuto 60, 3 gol, base 12,26. Risultati: 3 gol +2,49; 4 gol -12,26; 5 o piu'
gol +2,02.
- Distribuzione media modello/storico: 3 gol 0,60; 4 gol 0,28; 5 o piu' 0,12.
- Mercato: 4 gol 0,30, piu' alta -> si usa 0,30; le altre scalano di 0,70 / 0,72: 3 gol 0,583; 5+ gol
  0,117.
- Valore di tenere = 0,583 x 2,49 + 0,30 x (-12,26) + 0,117 x 2,02 = 1,45 - 3,68 + 0,24 = **-1,99**.
- Premio = 12,26 x 10% x 0,30 = **0,37**. Soglia = -1,99 - 0,37 = **-2,36**.
- "Se chiudo ora" -1,80: e' meglio di -2,36 -> **CHIUDE** in perdita di 1,80.
- "Se chiudo ora" -3,00: peggio di -2,36 -> **TIENE**.
- Con il tetto al 20%: 12,26 x 20% = 2,45; -3,00 e' oltre -2,45 -> tiene comunque.
- Regola fissa (senza dati del modello): 12,26 x 25% = 3,07. -1,80 non e' peggio di -3,07 con 3 gol
  -> CHIUDE; con 2 gol -> no (fuori dall'intervallo 3-4).
- Media di due distribuzioni: 4 gol 0,20 (modello) e 0,30 (storico) -> 0,25.

**Cosa vedi nell'app.** "uscita a modello (2t): chiudere (-1.80) vale piu' di tenere (-1.99 - premio
0.37, P4 30%)"; oppure "tenere vale ..."; "loss tollerata (ht): ... entro 25.0% di ...".

**Se qualcosa va storto.** Nessuna distribuzione disponibile: regola fissa. Probabilita' dei 4 gol
sporca: tenuta fra 0 e 1.

**Per il tecnico.** `engine.py:1171-1209` (`loss_exit_model`), `1146-1168` (`hold_expectation`),
`1135-1143` (`blend_totals`), `1010-1015` (`loss_exit_ok`); finestra `3501-3508` (`_loss_rule`);
chiamata `3540-3578`. Parametri `loss_exit_mode`, `loss_exit_risk_premium_pct`,
`loss_exit_p4_prudent`, `loss_exit_max_pct`, `loss_exit_emp_min_n`, `ht_loss_exit_enabled`,
`ht_loss_pct`, `ht_loss_goals_min`, `ht_loss_goals_max`, `h2_loss_exit_enabled`, `h2_loss_pct`,
`h2_loss_from_min`, `h2_loss_to_min`. Inventario A: schede 50, 54, 55, 56. Paper e live: uguale.

---

## 7. Tetto di perdita (rosa, protezione)

**Cosa fa.** Se "se chiudo ora" e' uguale o peggiore di -100% della base, chiude tutto con motivo
"tetto di perdita". Questa uscita e' una protezione: passa SEMPRE dal cancello delle uscite, anche
con le uscite manuali (schema 06).

**Quando.** Nella fase "coperti", dopo le altre tre domande.

**Numeri.** Tetto 100% della base (pagina: da 0 a 500; 0 = spento).

**Esempio con le cifre.** Base 12,26. "Se chiudo ora" -12,30: e' peggio di -12,26 -> CHIUDE
("cap perdita evento: -12.30"). "Se chiudo ora" -8,00 -> no, si passa a "Tiene".

**Cosa vedi nell'app.** "cap perdita evento: ..."; nella scheda Trade il tipo d'uscita "forzata".

**Se qualcosa va storto.** Con una quota mancante ("prezzi incompleti") nemmeno il tetto scatta.

**Per il tecnico.** `engine.py:3579-3583` (fuori area A). Parametro `event_loss_cap_pct`. Motivo
`loss_cap`. Paper e live: uguale.

---

## 8. Tiene (ambra, attesa)

**Cosa fa.** Se tutte le domande hanno risposto "no", Mike tiene la posizione. Unica eccezione:
se la copertura era stata comprata a meta' (prima tranche dopo un gol precoce) e sono passati 180
secondi dal suo abbinamento, torna a "Under scoperto" per comprare la seconda tranche, cioe' il
RESIDUO ricalcolato alla quota Over di quel momento (11a, riquadro 10). Se l'ora della prima tranche
non e' nota, compra subito.

**Quando.** Nella fase "coperti", alla fine delle domande.

**Numeri.** Seconda tranche 180 secondi dopo l'abbinamento della prima (pagina: da 0 a 900).

**Esempio con le cifre.** Prima tranche 1,13 euro a 6,60 abbinata alle 20:15:00. Alle 20:18:00 nessuna
uscita scatta: Mike torna a coprire e compra 0,90 euro a quota 8,00.

**Cosa vedi nell'app.** "tengo"; "seconda tranche: completo la copertura".

**Se qualcosa va storto.** Nessun caso particolare.

**Per il tecnico.** `engine.py:3593-3603` (fuori area A). Parametro `early_goal_cover2_delay_s`.
Paper e live: uguale.

---

## 9. Chiude tutto (verde, azione)

**Cosa fa.** Per ogni selezione con un ordine di chiusura calcolato (11a, riquadro 6):
1. L'importo di chiusura e' almeno 0,01 euro? No -> quella selezione non si chiude e resta al
   regolamento.
2. Ritira ogni altro ordine vivo sulla stessa selezione (per esempio una vecchia bancata di green
   appoggiata): due ordini nella stessa direzione abbinati entrambi ribalterebbero la posizione.
3. Piazza la chiusura: bancata o punta, alla quota e con l'importo del calcolo.
La fase passa a "chiusura" (il seguito, riprezzi e tentativi, e' nello schema 05).
La chiusura manuale dalla pagina usa lo stesso calcolo ma in due tempi: prima ritira TUTTI gli
ordini vivi, poi chiude (riquadro 1).

**Quando.** Dopo un "si'" della soglia, del cash out intelligente, dell'uscita in perdita o del tetto.

**Numeri.** Importo minimo di chiusura 0,01 euro. Tick "contro di noi" 0 (pagina: da 0 a 3).

**Esempio con le cifre.** Dall'esempio della soglia (+0,78): Mike banca 12,50 euro Under 3,5 a 1,20 e
banca 0,75 euro Over 4,5 a 20. Risultato bloccato: +2,50 sul mercato 3,5 (+2,375 netti) e -1,59 sul
4,5 -> **+0,78 netti**.

**Cosa vedi nell'app.** Due righe nuove nella scheda Trade ("chiusura Under", "chiusura Over"); la
fase "chiusura".

**Se qualcosa va storto.** Senza liquidita' sufficiente la chiusura resta in coda e viene riprezzata
(schema 05).

**Per il tecnico.** `engine.py:1754-1783` (`_close_actions`), `1717-1734` (`size_chiudibile`),
`1737-1751` (`ordini_vivi_su`), `1815-1816` (`_pending_closings`, usata a `3607`). Inventario A:
schede 82, 83, 84, 87. Paper e live: uguale.

---

## 10. Guardie e freni (rosa, blocco) - RIMANDO ALLO SCHEMA 08

**Cosa fa.** Ogni decisione, anche quella di copertura, passa in quest'ordine: freno della copertura
(3 rifiuti con lo stesso codice o meno di 15 secondi dall'ultimo tentativo), mai due bancate sulla
stessa selezione, mai sovracopertura. Il dettaglio e' nello schema 08.

**Quando / Numeri / Esempio / App / Se va storto.** Vedi schema 08.

**Per il tecnico.** `engine.py:2023-2074`, `1901-1951`, `1972-2020`; ordine in `decide`
`2208-2212`. Inventario A: schede 88-95 (rimandate).

---

## 11. Cancello uscite (grigio, rimando) - RIMANDO ALLO SCHEMA 06

**Cosa fa.** Decide CHI esegue un'uscita: con le uscite automatiche spente (di serie) green, uscita
al fischio, chiusure e green del re-ingresso diventano una proposta da firmare (firma valida 120
secondi); il tetto di perdita passa sempre. Il dettaglio e' nello schema 06.

**Quando / Numeri / Esempio / App / Se va storto.** Vedi schema 06.

**Per il tecnico.** `engine.py:2225-2431` (`gate_uscite`). Inventario A: schede 98-107 (rimandate).

---

## Frecce

- Ogni giro -> Regola della fase: "si opera" = fase non finale, partita non chiusa dall'utente fuori
  app, nessuna chiusura manuale in corso.
- Regola della fase -> Quando coprire: "Under scoperto" = fase "Under scoperto" in gioco.
- Regola della fase -> Soglia 5%: "coperti" = fase "coperti", selezioni gestibili, tutte le quote
  presenti.
- Soglia 5% -> Chiude tutto: "si'" = se chiudo ora >= 5% della base (0,613 su 12,26).
- Soglia 5% -> Cash out intelligente: "no".
- Cash out intelligente -> Chiude tutto: "si'" = sopra il 2% E (3+ gol, oppure a un passo dalla soglia
  con fase calda, oppure valore dell'attesa piu' basso).
- Cash out intelligente -> Perdita a modello: "no".
- Perdita a modello -> Chiude tutto: "si'" = intervallo o minuto 46-85, 3-4 gol, e se chiudo ora >=
  valore di tenere - premio (o regola fissa: >= -25% della base).
- Perdita a modello -> Tetto di perdita: "no".
- Tetto di perdita -> Chiude tutto: "si'" = se chiudo ora <= -100% della base.
- Tetto di perdita -> Tiene: "no".
- Chiude tutto -> Guardie e freni: sempre.
- Guardie e freni -> Cancello uscite: sempre.

---

## Punti da decidere

Differenze dalla Costituzione (`Betfair/mike/COSTITUZIONE_MIKE.md`):
1. **Gol minimi dell'uscita in perdita**: §6 dice 2, §3 Fase 5 dice "solo con 2, 3 o 4 gol"; il codice
   usa 3 (`config.py:287`). Con 2 gol Mike oggi non chiude mai in perdita.
2. **Uscite automatiche**: la Costituzione (§15.7-ter) dice che restano automatiche; il codice di
   serie le propone all'utente (schema 06).
3. **Ordine delle guardie**: la Costituzione chiama "ultima parola" la regola delle due bancate; nel
   codice dopo vengono anche la sovracopertura e il cancello, e il freno della copertura viene
   prima (schema 08).

Cose strane:
4. **Gol mancanti contati come zero** nell'attesa della copertura e nel cash out intelligente: la
   regola scritta dice "ogni dato mancante = si copre", ma con i gol mancanti Mike puo' ASPETTARE; e
   il "punteggio caldo" non scatta. `engine.py:1225`, `1099`.
5. **Un parametro per due cose**: l'orizzonte del cash out intelligente (5 minuti) e' lo stesso
   parametro dell'attesa della copertura (`cover_wait_step_min`): cambiarne uno cambia l'altro.
6. **Quota mancante = nessuna uscita, nemmeno il tetto di perdita** (`engine.py:3525`).
7. **Chiusura manuale ferma dopo 20 tentativi**: resta "attendo il fill" senza riprezzare piu'
   (`engine.py:2100-2103`).
8. **Parametro `ko_green_retry_s` (5 secondi)**: nessuno lo legge; un commento
   (`engine.py:1525-1529`) dice ancora che l'uscita al fischio lo aspetta. Cambiarlo dalla pagina non
   ha effetto.
9. **Tetto di perdita al 100% della base "capitale puntato"**: con la copertura in piedi "se chiudo
   ora" arriva a -12,26 solo se anche la copertura non vale piu' nulla; da valutare se il tetto
   misura quello che si vuole (vedi anche 11a, punto 5).
10. **Chiusura forzata in un colpo solo** (`force_flat_actions`): nessun chiamante in produzione, solo
    nei test.

## Punti non chiariti

- Il "risparmio atteso" della copertura e le distribuzioni dei gol arrivano dal servizio: non ho letto
  come li calcola.
- Chi scrive "aperture ferme" e con quali cause esatte: e' il servizio, non letto qui.

## Schede dell'inventario rimandate ad altri schemi

- Schema 08 (guardie sugli ordini e freni): 65, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 88, 89,
  90, 91, 92, 93, 94, 95.
- Schema 06 (cancello delle uscite manuali / automatiche): 98, 99, 100, 101, 102, 103, 104, 105,
  106, 107.
