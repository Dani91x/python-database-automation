# Mike - Capitolo 5b: piatto, rientro sull'Under 4,5 e regolamento

Schema: `05b_chiusura_e_rientro.html` (sorgente `05b_chiusura_e_rientro.workflow.json`).
Viene dopo `05a_uscite_a_posizione_coperta` (le uscite a posizione coperta e la chiusura in corso).

**Schede dell'inventario usate** (`SCHEMI_BOT/mike/inventario/B_strategia.md`): 46, 47, 48, 49, 50, 51, 52; la
premessa (uscite manuali); le righe `FLAT`, `REENTRY_PENDING`, `REENTRY_OPEN`, `REENTRY_GREEN_PENDING` e
«qualunque -> `SETTLING`» della tabella delle transizioni; Differenze 11; Cose strane 3, 7. Dall'area ordini
(`C_servizio_e_ordini.md`): scheda 24 (tipi d'ordine), Differenze 5 e 14, Cose strane 15.

**Colori** (uguali in tutti gli schemi di Mike): ambra = attesa · viola = decisione · verde = profitto bloccato
· rosa = perdita o blocco · azzurro = azione (un ordine parte) · grigio = fermo o fine.

**Chi decide.** Di serie le uscite sono MANUALI: la banca di green del rientro (e la sua chiusura a tempo) e'
una PROPOSTA che parte solo se la approvi. Sono SEMPRE AUTOMATICI: la puntata di rientro (e' un ingresso, non
un'uscita), il ritiro della sua parte non abbinata, il regolamento.

**Esempio usato nelle schede.** Primo ingresso della partita: punta 10,00 EUR Under 3,5 a 1,50. Al 2' l'uscita
al fischio si abbina: +0,13 EUR, posizione chiusa in profitto. Al 30' la partita e' 1-0.

---

## 1. Piatto (riquadro ambra)

**Cosa fa**: Mike ha chiuso la posizione (o non ha piu' niente in gioco). A ogni giro rifa' i controlli dei
riquadri 2-4 per sapere se deve tornare alle uscite, restare fermo o rientrare.

**Quando**: dopo la chiusura in corso (capitolo 05a), dopo «nessuna esposizione gestibile», dopo l'uscita al
fischio abbinata per intero (capitolo 03), o alla fine di un rientro.

**Numeri**: nessuno.

**Esempio con le cifre**: uscita al fischio abbinata al 2' (+0,13 EUR): Mike e' in Piatto con il rientro
permesso.

**Cosa vedi nell'app**: «flat», «chiuso (profit)» o i motivi dei riquadri seguenti.

**Se qualcosa va storto**: niente ordini in giro: e' una casella di attesa.

**Per il tecnico**: stato `FLAT`, `engine.py:3677-3708` (`_decide_flat`).

---

## 2. Tutto chiuso? (riquadro viola)

**Cosa fa**: controlla che non resti rischio in gioco. Se resta, decide se si puo' ancora chiudere.

**Quando**: primo controllo di ogni giro in Piatto.

**Numeri**: una selezione e' aperta se vincita e perdita differiscono di almeno 0,01 EUR; e' «in gioco» se i
gol non l'hanno gia' decisa.

**Esempio con le cifre**:
- Tutto chiuso: dopo il cash out non resta niente -> riquadro 3.
- Resta rischio chiudibile: la banca di chiusura dell'Over 4,5 si e' abbinata per 0,60 EUR su 0,99 -> resta
  un'esposizione chiudibile -> riquadro 9 (torna alle uscite).
- Resta un residuo minuscolo: servirebbe una banca da 0,004 EUR -> riquadro 10.

**Cosa vedi nell'app**: «esposizione residua» o «residuo sotto il minimo Betfair: si porta al regolamento».

**Se qualcosa va storto**: se mancano i prezzi per calcolare la chiusura, il residuo NON e' dichiarato
«minimo»: Mike torna alle uscite, dove aspettera' i prezzi.

**Per il tecnico**: `engine.py:3678-3683`; `residuo_non_chiudibile` 3654-3674; `size_chiudibile` 1717-1734.

---

## 3. Rientro permesso? (riquadro viola)

**Cosa fa**: controlla, nell'ordine, se il rientro sull'Under 4,5 e' ammesso in questa partita:
1. Hai chiuso tu la partita a mano? Se si', niente rientro («rientro disabilitato (chiusura manuale)»).
2. Il rientro e' acceso nei parametri? Se no, niente rientro.
3. L'ultima chiusura era in profitto? Se no (perdita all'intervallo, nel secondo tempo, tetto), niente rientro.
4. Il rientro e' gia' stato fatto (o tentato) in questa partita? Se si', niente rientro.

**Quando**: in Piatto, tutto chiuso.

**Numeri**: rientro acceso di serie; una volta sola per partita.

**Esempio con le cifre**: chiusura al fischio a +0,13 EUR -> permesso. Chiusura in perdita all'intervallo a
-3,31 EUR -> non permesso, Mike resta piatto.

**Cosa vedi nell'app**: «flat» o «flat: rientro disabilitato (chiusura manuale)».

**Se qualcosa va storto**: a bot fermo il servizio spegne il rientro: niente ingressi nuovi.

**Per il tecnico**: `engine.py:3684-3687`; `reentry_enabled` True (`config.py:294`); permesso scritto in
`_decide_closing` 3625 e in `_decide_ko_green` (capitolo 03); spento a bot fermo `service.py:1274`.

---

## 4. Condizioni del rientro (riquadro viola)

**Cosa fa**: controlla, nell'ordine, la situazione della partita. Alla prima che non va, resta piatto e scrive
il motivo.
1. I dati sono abbastanza freschi per un ordine, e gol e minuto sono noti? Se no: «dati feed mancanti».
2. I gol sono esattamente 1? (almeno 1 e al massimo 1) Se no: «N gol fuori range re-ingresso».
3. Il minuto e' al massimo il 45'? Se no: «oltre il minuto di re-ingresso».
4. Il mercato Under 4,5 c'e', ha una quota di punta ed e' aperto? Se no: «mercato Under 4.5 ...».
5. La quota di punta dell'Under 4,5 e' piu' alta del prezzo del PRIMO ingresso della partita? Se no: resta piatto.
6. Al miglior prezzo ci sono almeno 10,00 EUR disponibili? Se no: «liquidita re-ingresso».
7. C'e' spazio sotto il tetto di capitale per partita (spento di serie)? Se no: «cap liability partita».

**Quando**: in Piatto, rientro permesso.

**Numeri**: gol 1 (massimo 1); fino al 45'; quota Under 4,5 > quota del primo ingresso (controllo acceso);
liquidita' >= 10,00 EUR (importo x 1,0); tetto per partita 0 = spento.

**Esempio con le cifre**: 1-0 al 30', Under 4,5 a 1,70 con 25 EUR disponibili, primo ingresso a 1,50: tutte si'.
Con 1-0 al 50': no (oltre il 45'). Con Under 4,5 a 1,45: no (non supera 1,50). Con 2-0: no.

**Cosa vedi nell'app**: i motivi fra virgolette.

**Se qualcosa va storto**: niente ordine: Mike riprova al giro dopo finche' una condizione cambia (per esempio
passa il 45').

**Per il tecnico**: `engine.py:3688-3705`; `reentry_max_goals` 1, `reentry_until_min` 45,
`reentry_price_min_over_entry` True (`config.py:296-300`); `pre_min_back_size_factor` 1,0; `stake` 10;
`max_liability_per_match` 0 (`config.py:308`); `liability_room` 1707-1714.

---

## 5. Punta Under 4,5 (riquadro azzurro) - SEMPRE AUTOMATICA

**Cosa fa**: punta 10,00 EUR sull'Under 4,5 al miglior prezzo di punta e ne segue l'abbinamento.

**Quando**: tutte le condizioni del riquadro 4 sono si'.

**Numeri**: importo 10,00 EUR; quota = miglior punta; attesa massima 60 secondi.

**Controlli dell'abbinamento, nell'ordine**:
1. La puntata non c'e' piu'? -> Piatto.
2. Non e' piu' viva e non ha abbinato niente? -> Piatto, rientro segnato come fatto (non si riprova).
3. Abbinata per intero: il mercato Under 4,5 e' aperto? Se no, aspetta. Se si', prepara la banca di green
   (riquadro 6).
4. Ancora viva dopo 60 secondi: con una parte abbinata -> ritira il resto e tiene la parte abbinata
   (riquadro 6); senza niente abbinato -> ritira e va a Piatto, rientro fatto.
5. Altrimenti aspetta.

**Esempio con le cifre**: punta 10,00 EUR a 1,70 abbinata. Se l'Under 4,5 vince: +7,00 EUR; se perde: -10,00 EUR.

**Cosa vedi nell'app**: «re-ingresso Under 4.5», «attesa fill re-ingresso», «re-ingresso abbinato».

**Se qualcosa va storto**: la puntata parte «tutto o niente» (area ordini, scheda 24): o si abbina subito o viene
annullata, e allora il rientro e' perso per questa partita.

**Paper o live**: identico nella strategia; in paper la esegue il simulatore, in live Betfair.

**Per il tecnico**: ordine `engine.py:3706-3708` (ruolo `reentry`, LAPSE); stato `REENTRY_PENDING`,
`_decide_reentry_pending` 3711-3740; `pre_entry_ttl_s` 60.

---

## 6. Green appoggiata (riquadro verde) - MANUALE

**Cosa fa**: appena il rientro e' abbinato, Mike prepara una banca sull'Under 4,5 due tick sotto il prezzo di
punta, per tutta l'esposizione, e la lascia sul libro fino a fine partita. Se sparisce (ritirata da Betfair a
una sospensione) la rimette.

**Quando**: dal riquadro 5 (abbinato), poi a ogni giro della casella «rientro aperto».

**Controlli a ogni giro, nell'ordine**:
1. La posizione e' piatta (green abbinata)? -> ritira eventuali green vive, Piatto, rientro fatto.
2. E' acceso un minuto limite ed e' arrivato? -> riquadro 11.
3. Non c'e' una green viva? Mercato Under 4,5 non aperto: aspetta. Mercato aperto: banca a (prezzo medio - 2
   tick) per l'esposizione netta. Se la stessa identica banca e' gia' stata rifiutata dal mercato, non la ripete.
4. Altrimenti «green sul book».

**Numeri**: 2 tick sotto il prezzo di punta.

**Esempio con le cifre**: punta 10,00 EUR a 1,70 -> banca 10,12 EUR a 1,68.
- Se la banca si abbina: circa **+0,12 EUR** qualunque sia il risultato (lordo; circa +0,11 netto).
- Se non si abbina fino alla fine: finisce con 4 gol o meno **+7,00 EUR** (netto +6,65); con 5 o piu' **-10,00 EUR**.

**Cosa vedi nell'app**: con le uscite manuali la proposta «Mike vorrebbe uscire: uscita del re-ingresso» con il
pulsante **Approva uscita**; poi «green re-ingresso appoggiata», «re-ingresso aperto, green sul book»,
«re-ingresso chiuso».

**Se qualcosa va storto**:
- Mentre il rientro e' aperto Mike NON compra copertura, NON fa cash out e NON ha uscite in perdita: l'unica
  protezione e' questa banca.
- Con prezzi non vivi la banca non parte (anche in live): verificato sul codice del servizio
  (`service.py:4462-4477`). Mike la ripropone quando i prezzi tornano vivi.
- La sospensione che fa sparire la banca e' letta dal mercato **Under 3,5**, non dall'Under 4,5 su cui la banca
  sta: verificato sul codice (`service.py:2881-2882`). Vedi «Punti da decidere», n. 2.

**Paper o live**: la banca resta sul libro in entrambi (in live, se spegni «uscite appoggiate in live», diventa
una banca al miglior prezzo, area ordini).

**Per il tecnico**: prima banca `engine.py:3717-3734` (ruolo `reentry_green`); stato `REENTRY_OPEN`,
`_decide_reentry_open` 3743-3787; `reentry_green_ticks` 2 (`config.py:295`); appoggiata perche'
`_is_resting_leg` (`service.py:1330-1346`) con `pre_exit_mode` «resting»; proposta da `engine.gate_uscite`
2337-2431 (categoria `reentry_green`). Lo stato avanza a `REENTRY_OPEN` anche se la banca resta proposta.

---

## 7. Resta piatto (riquadro grigio)

**Cosa fa**: non c'e' niente da fare: niente rischio e niente rientro. Mike aspetta la fine del mercato.

**Quando**: dal riquadro 3 o 4 con un «no», o dopo un rientro chiuso o non abbinato.

**Numeri**: nessuno.

**Esempio con le cifre**: chiusura in perdita a -3,31 EUR all'intervallo: resta piatto, risultato della partita
-3,31 EUR (piu' quanto bloccato nei cicli pre-partita).

**Cosa vedi nell'app**: «flat» con il motivo.

**Se qualcosa va storto**: niente.

**Per il tecnico**: stato `FLAT` (rami che restituiscono `FLAT` in `engine.py:3684-3705`).

---

## 8. Regolamento (riquadro grigio) - SEMPRE AUTOMATICO

**Cosa fa**: quando il mercato chiude, da qualunque casella, Mike ritira ogni ordine ancora vivo, aspetta il
punteggio finale e calcola il risultato di ogni gamba, con la commissione per mercato.

**Quando**: mercato chiuso.

**Numeri**: commissione 5 % sul netto positivo di ogni mercato.

**Esempio con le cifre**: rientro con green non abbinata, finale 2-1 (3 gol): Under 3,5 chiuso al fischio +0,13;
Under 4,5 vinto +7,00 (netto +6,65). Risultato circa **+6,78 EUR**. Finale 3-2: circa **-9,87 EUR**.

**Cosa vedi nell'app**: «mercato chiuso», «attesa punteggio finale», «regolato T=3».

**Se qualcosa va storto**: con un ordine a esito ignoto il regolamento si FERMA («regolamento sospeso: un ordine ha
esito ignoto») finche' non si chiarisce: il risultato non viene inventato.

**Per il tecnico**: `engine.py:2440-2460` (`SETTLING` -> `SETTLED`, `settle_legs`); partita mai operata
2466-2469.

---

## 9. Torna alle uscite (riquadro ambra, fascia «Ritorni e casi rari»)

**Cosa fa**: in Piatto resta un rischio che si puo' ancora chiudere: Mike torna in posizione coperta (capitolo
05a) e rifa' i controlli d'uscita.

**Quando**: riquadro 2, rischio in gioco chiudibile (o prezzi mancanti per dirlo).

**Numeri**: nessuno.

**Esempio con le cifre**: la banca dell'Over 4,5 da 0,99 EUR si e' abbinata per 0,60: resta aperta l'Over per 0,39
EUR di punta netta. Mike torna in posizione coperta e al giro dopo propone (o esegue) la chiusura del residuo.

**Cosa vedi nell'app**: «esposizione residua».

**Se qualcosa va storto**: vedi capitolo 05a, «Punti da decidere», n. 3 e 4.

**Per il tecnico**: `engine.py:3683` (verso `LIVE_COVERED`).

---

## 10. Residuo minimo (riquadro grigio, fascia «Ritorni e casi rari»)

**Cosa fa**: il rischio rimasto e' cosi' piccolo che ogni ordine per chiuderlo sarebbe sotto 0,01 EUR. Mike non
lo insegue: lo tiene fino al regolamento e lo dice una volta.

**Quando**: riquadro 2, tutti gli ordini di chiusura possibili sotto 0,01 EUR.

**Numeri**: 0,01 EUR.

**Esempio con le cifre**: resterebbe una banca da 0,004 EUR: al regolamento vale meno di un centesimo in piu' o
in meno.

**Cosa vedi nell'app**: «residuo sotto il minimo Betfair: si porta al regolamento» (il testo fa pensare ai 2 EUR
di Betfair, ma la soglia vera e' 0,01 EUR).

**Se qualcosa va storto**: se il calcolo va in errore o non c'e' nessun ordine calcolabile, il residuo NON e'
considerato minimo (riquadro 9).

**Per il tecnico**: `engine.py:3679-3682`; `residuo_non_chiudibile` 3654-3674; `size_chiudibile` 1717-1734
(soglia `SUBMIN_FLOOR` 0,01).

---

## 11. Chiusura a tempo del rientro (riquadro azzurro) - MANUALE, spenta di serie

**Cosa fa**: se accendi un minuto limite, a quel minuto Mike ritira la green appoggiata e chiude il rientro
bancando al miglior prezzo, anche in perdita. Poi la segue: riprezzo dopo 10 secondi, massimo 20 tentativi.

**Quando**: rientro aperto, minuto limite maggiore di 0 e raggiunto. Con il limite a 0 (di serie) non succede mai.

**Controlli**:
1. «Tieni se in perdita» acceso? -> Mike tiene («oltre il limite: tengo») e non chiude.
2. Altrimenti ritira la green e, se il mercato e' aperto con un prezzo di banca, banca al miglior prezzo.
3. Chiusura in attesa: posizione piatta o banca abbinata -> Piatto, rientro fatto; banca morta senza
   abbinamento -> torna al rientro aperto; ferma da 10 secondi e meno di 20 tentativi -> ritira e rimanda al
   miglior prezzo.

**Numeri**: minuto limite 0 = spento; «tieni se in perdita» spento; riprezzo 10 secondi; 20 tentativi.

**Esempio con le cifre** (limite messo a 70'): punta 10,00 EUR a 1,70.
- Al 70' l'Under 4,5 si banca a 1,40: banca 12,14 EUR -> circa **+2,14 EUR** in ogni risultato.
- Al 70' si banca a 2,20: banca 7,73 EUR -> circa **-2,27 EUR** in ogni risultato. Tenendo: +7,00 o -10,00 EUR.

**Cosa vedi nell'app**: «re-ingresso: chiusura a mercato», «re-ingresso: riprezzo chiusura», «re-ingresso chiuso».

**Se qualcosa va storto**: il riprezzo si blocca sulla regola «mai due banche» e la chiusura torna al rientro
aperto (inventario B, Cose strane 3); al giro dopo, col minuto ancora oltre il limite, Mike richiude.

**Per il tecnico**: `engine.py:3752-3764` (motivo `reentry_time`); stato `REENTRY_GREEN_PENDING`,
`_decide_reentry_green_pending` 3790-3808; `reentry_exit_until_min` 0 e `reentry_hold_if_loss` False
(`config.py:299-301`); `close_retry_s` 10, `close_max_attempts` 20.

---

## Come Mike scrive le decisioni sulla partita (scheda comune a tutto il capitolo 5)

**Cosa fa**: dopo ogni decisione Mike salva sulla partita i nuovi valori, la nuova casella e, per ogni ordine da
mandare, una riga «in attesa» con codice `ruolo-ciclo-progressivo`. Le chiusure scrivono quale apertura chiudono.
I ritiri non cambiano le righe: le cambia il servizio quando Betfair (o il simulatore) conferma.

**Per il tecnico**: `apply_decision` `engine.py:3814-3869`.

## Tipi d'ordine del capitolo 5

| Ordine | Selezione | Punta/banca | Quota | Tipo vero (area ordini, scheda 24) |
|---|---|---|---|---|
| Chiusura Under 3,5 | Under 3,5 | banca | miglior banca | tutto o niente, cade alla sospensione |
| Chiusura Over 4,5 | Over 4,5 | banca | miglior banca | tutto o niente, cade alla sospensione |
| Chiusura Under 4,5 (cash out o a tempo) | Under 4,5 | banca | miglior banca | appoggiata (di serie), cade alla sospensione |
| Rientro | Under 4,5 | punta 10,00 EUR | miglior punta | tutto o niente, cade alla sospensione |
| Green del rientro | Under 4,5 | banca | prezzo medio - 2 tick | appoggiata, cade alla sospensione |

Nessun ordine del capitolo resta valido in gioco dopo una sospensione. Con prezzi non vivi non parte nessuno di
questi ordini.

---

## Frecce

- Piatto -> Tutto chiuso?: a ogni giro.
- Tutto chiuso? -> Rientro permesso? («si'»): nessuna selezione aperta ancora in gioco.
- Tutto chiuso? -> Torna alle uscite («chiudibile»): rischio in gioco e almeno una chiusura >= 0,01 EUR (o prezzi
  mancanti).
- Tutto chiuso? -> Residuo minimo («sotto 0,01»): rischio in gioco ma ogni chiusura possibile < 0,01 EUR.
- Rientro permesso? -> Condizioni («si'»): non chiusa a mano, rientro acceso, ultima chiusura in profitto, rientro
  non ancora fatto.
- Rientro permesso? -> Resta piatto («no»): una delle quattro manca.
- Condizioni -> Punta Under 4,5 («tutte si'»): dati freschi, 1 gol, minuto <= 45', Under 4,5 aperto, quota >
  primo ingresso, liquidita' >= 10,00 EUR, spazio sotto il tetto.
- Condizioni -> Resta piatto («no»): una condizione manca (si ricontrolla al giro dopo).
- Punta Under 4,5 -> Green appoggiata («abbinata»): abbinata per intero e Under 4,5 aperto, oppure 60 secondi con
  una parte abbinata.
- Punta Under 4,5 -> Resta piatto (freccia non disegnata): non abbinata, o 60 secondi senza abbinamento.
- Green appoggiata -> Resta piatto (freccia non disegnata): green abbinata, posizione piatta.
- Green appoggiata -> Chiusura a tempo («minuto limite»): limite > 0 e raggiunto.
- Green appoggiata, Resta piatto -> Regolamento («fischio finale»): mercato chiuso. Vale da qualunque casella.

---

## Punti da decidere

1. **Prezzi non vivi = nessun ordine, chiusure e green comprese** (area C, Differenze 5; verificato sul codice,
   `service.py:709-717` e `4462-4477`). La Costituzione §5 dice «chiusure permesse».
2. **La sospensione si legge solo dall'Under 3,5** (area C, Differenze 14 e Cose strane 15; verificato sul codice,
   `service.py:2881-2882`). La green del rientro sta sull'Under 4,5: se l'Under 4,5 viene sospeso e l'Under 3,5 no,
   Mike non annota la sospensione e non rilegge la green alla riapertura. Da decidere se leggere il mercato
   giusto.
3. **Il rientro non ha protezioni** (inventario B, Differenze 11): niente copertura, niente cash out, niente
   uscita in perdita; se la green non e' approvata o non si abbina, la perdita e' -10,00 EUR con 5 o piu' gol.
4. **«Tieni se in perdita» tiene sempre** (letto sul codice, `engine.py:3754-3755`): se lo accendi Mike non chiude
   al minuto limite nemmeno quando e' in profitto. Il nome fa pensare a «tieni solo se in perdita».
5. **La chiusura a tempo potrebbe partire senza firma** (da confermare, letto sul codice e non provato col replay):
   se la green del rientro e' gia' stata approvata, esiste un ordine dello stesso tipo nel ciclo e la chiusura a
   tempo (stesso tipo) viene considerata «uscita gia' in corso» (`engine.py:2269-2285`). Lo stesso vale per la
   green rimessa dopo una sospensione (questo e' voluto).
6. **Rientro perso al primo mancato abbinamento**: la puntata parte «tutto o niente»; se non si abbina il rientro
   e' segnato come fatto e non si riprova (inventario C, scheda 24, non verificato di persona).
7. **Testo «residuo sotto il minimo Betfair»** fa pensare ai 2 EUR; la soglia vera e' 0,01 EUR (inventario B, Cose
   strane 7).

## Punti non chiariti

- Le cifre degli esempi sono arrotondate a mano al centesimo.
- Non ho riletto il servizio per sapere in che momento marca come «fatto» un rientro annullato «tutto o niente»
  (dipende da quando la gamba risulta non viva e senza abbinato).
