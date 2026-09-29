# Mike - Capitolo 5a: le uscite a posizione coperta

Schema: `05a_uscite_a_posizione_coperta.html` (sorgente `05a_uscite_a_posizione_coperta.workflow.json`).
Il capitolo continua in `05b_chiusura_e_rientro` (piatto, rientro sull'Under 4,5, regolamento).

**Schede dell'inventario usate** (`SCHEMI_BOT/mike/inventario/B_strategia.md`): 37 (solo il richiamo del ritiro
dell'ultimo ingresso), 39, 40, 41, 42, 43, 44, 45, 51, 52; la premessa (uscite manuali, «mai due lay»,
ordini a esito ignoto); le righe `LIVE_COVERED` e `LIVE_CLOSING` della tabella delle transizioni; Differenze 5;
Cose strane 3, 4, 15, 16. Dall'area ordini (`C_servizio_e_ordini.md`): schede 16, 17, 19, 22, 24; Differenze 5;
Cose strane 1-2. Le schede 46-50 stanno nel capitolo 05b.

**Colori dello schema** (uguali in 05a e 05b):
ambra = attesa · viola = decisione · verde = profitto bloccato · rosa = perdita o blocco · azzurro = azione (un
ordine parte) · grigio = il tuo pulsante (in 05b: fermo o fine). Sono i colori di tutti gli schemi di Mike.

**Chi decide ogni uscita.** Di serie le uscite sono MANUALI (interruttore «uscite automatiche» spento): Mike
calcola l'uscita e la mette nella scheda della partita come PROPOSTA; parte solo se la approvi. Sono SEMPRE
AUTOMATICI, anche a interruttore spento: la copertura Over 4,5, il tetto di perdita della partita, il ritiro
degli ordini d'ingresso, il regolamento. Se accendi l'interruttore, Mike esegue da solo anche cash out e
uscite in perdita.

**La posizione d'esempio usata in tutte le schede.**
Mike ha puntato 10,00 EUR sull'Under 3,5 a quota 1,50 e 2,26 EUR sull'Over 4,5 a quota 6,6 (la copertura).
- Capitale investito (la «base» delle percentuali): 10,00 + 2,26 = **12,26 EUR**.
- Se Mike tiene tutto fino alla fine, al netto della commissione del 5 %:
  - finisce con 0, 1, 2 o 3 gol: Under vinto +5,00 (netto +4,75), Over perso -2,26 -> **+2,49 EUR**;
  - finisce con 4 gol: Under perso -10,00, Over perso -2,26 -> **-12,26 EUR**;
  - finisce con 5 o piu' gol: Under perso -10,00, Over vinto +12,66 (netto +12,02) -> **+2,02 EUR**.

---

## 1. Posizione coperta (riquadro ambra, in alto a sinistra)

**Cosa fa**: e' la casella in cui Mike sta quando ha l'Under 3,5 in mano e la copertura sull'Over 4,5 e'
comprata (o saltata). A ogni giro rifa' da capo, nell'ordine, i controlli dei riquadri 2-7. Non piazza
nessun ordine di suo. In piu', a ogni giro ritira la parte non abbinata dell'ultimo ingresso della
pre-partita, se dal fischio di calendario sono passati almeno 120 secondi (sempre automatico).

**Quando**: Mike arriva qui dalla copertura (capitolo 04), da «esposizione residua» (capitolo 05b), o
tornandoci dopo un «tengo». Il giro si ripete circa ogni 0,5-2 secondi.

**Numeri**: ritiro dell'ultimo ingresso dopo 120 secondi dal fischio di calendario.

**Esempio con le cifre**: fischio alle 21:00. Alle 21:02:00 l'ultimo ingresso (punta 10,00 EUR Under 3,5 a
1,45) ha abbinato 6,00 EUR: Mike ritira i 4,00 EUR non abbinati. Posizione: Under 3,5 10,00 EUR a 1,50 +
Over 4,5 2,26 EUR a 6,6.

**Cosa vedi nell'app**: la partita in gioco con la posizione coperta; nell'attivita' la voce del valore
di cash out a ogni giro (netto, lordo, per selezione, percentuale della base).

**Se qualcosa va storto**: se un ordine della partita ha esito ignoto, Mike toglie solo gli ordini che
AUMENTANO il rischio; le uscite e il tetto di perdita restano valutati.

**Per il tecnico**: stato `LIVE_COVERED`, `engine.py:3511-3603` (`_decide_covered`); ritiro del PERSIST
`_late_persist_cancel` 3415-3422, chiamato a 3514. Il servizio manda l'ultimo ingresso come LAPSE + FOK
(area C, Differenze 1): nel codice di oggi non esiste un residuo PERSIST vero da ritirare.

---

## 2. Resta rischio? (riquadro viola)

**Cosa fa**: controlla due cose. Prima: c'e' ancora almeno una selezione aperta il cui esito non e' gia'
deciso dai gol? Poi: Mike ha tutti i prezzi (miglior punta e miglior banca) per calcolare «quanto incasso se
chiudo tutto adesso»?

**Quando**: primo controllo di ogni giro a posizione coperta.

**Numeri**:
- Una selezione e' «aperta» se la differenza fra quanto vince e quanto perde e' almeno 0,01 EUR.
- Una selezione e' «gia' decisa» quando i gol superano la sua linea: con 4 gol l'Under 3,5 e' perso; con 5
  gol l'Over 4,5 e' vinto e l'Under 4,5 e' perso.
- Valore di cash out = per ogni selezione ancora in gioco, il profitto che si blocca bancando al miglior
  prezzo (il peggiore dei due esiti); per ogni selezione gia' decisa, il suo esito. Commissione del 5 %
  per mercato, solo sul netto positivo.
- Base = capitale investito: somma delle puntate d'apertura ancora abbinate (Under 3,5, seconda
  puntata, Over 4,5, rientro). Si puo' cambiare in «solo Under» dall'interfaccia.

**Esempio con le cifre**:
- Nessuna selezione in gioco: 5-0 al 70'. Under 3,5 perso (-10,00), Over 4,5 vinto (+12,66): tutto
  deciso. Mike va a **Piatto** con «nessuna esposizione gestibile» e aspetta il regolamento (+2,02 EUR netti).
- Rischio aperto: 0-0 al 40'. Base 12,26 EUR. Mike passa al riquadro 4 (cash out).

**Cosa vedi nell'app**: «nessuna esposizione gestibile» quando va a piatto.

**Se qualcosa va storto**: se manca anche un solo prezzo di una selezione in gioco, vale il riquadro 3.

**Per il tecnico**: `engine.py:3512-3513` (`live_open_selections` 678-681, `selection_decided` 632-646);
valore `cashout_value` 737-805; base `cashout_base` 1676-1681 (`invested` 700-704), parametro
`cashout_base` = «total» (`config.py:230`), `cashout_place_at_ticks` = 0 (`config.py:231`). Passando a
`FLAT` da qui il permesso di rientro NON cambia.

---

## 3. Prezzi incompleti (riquadro ambra, fascia «Attese e ritorni»)

**Cosa fa**: se per una selezione ancora in gioco manca la miglior punta o la miglior banca, Mike non puo'
calcolare il valore di cash out. Non decide nessuna uscita e resta dov'e'.

**Quando**: a ogni giro in cui un prezzo manca (tipico subito dopo un gol, mercato sospeso).

**Numeri**: nessuno.

**Esempio con le cifre**: 1-0 al 23', l'Over 4,5 e' sospeso e non ha prezzo di banca. Mike resta in
posizione coperta con «prezzi incompleti». Al giro in cui il prezzo torna, rifa' tutti i controlli.

**Cosa vedi nell'app**: «prezzi incompleti».

**Se qualcosa va storto**: con i prezzi mancanti **anche il tetto di perdita (riquadro 6) non viene
valutato**: tutti i controlli d'uscita aspettano il ritorno dei prezzi.

**Per il tecnico**: `engine.py:3525-3526` (`cv.complete` falso).

---

## 4. Cash out a profitto (riquadro verde) - MANUALE

**Cosa fa**: chiude tutte le selezioni aperte quando il profitto netto bloccabile e' almeno il 5 % della
base. Prima di quella soglia puo' chiudere lo stesso con il «cash out intelligente», quando tenere non vale
il rischio.

**Quando**: posizione coperta, tutti i prezzi presenti. E' il primo controllo d'uscita del giro.

**Numeri**:
- **Soglia fissa**: netto bloccabile >= 5 % della base.
- **Cash out intelligente** (acceso di serie). Regole in quest'ordine:
  1. Il netto bloccabile e' almeno il 2 % della base? Se no, non chiude mai.
  2. I gol sono 3 o piu'? Se si', chiude («punteggio caldo»).
  3. Il netto e' «vicino alla soglia», cioe' al massimo 2 punti di percentuale sotto il 5 %? E insieme: la
     probabilita' di un gol nei prossimi 3 minuti e' almeno il 10 %, oppure la pressione offensiva e'
     almeno 1,15? Se si', chiude («fase calda»).
  4. Se ci sono il modello e la probabilita' di gol: Mike stima il valore di aspettare 5 minuti = (probabilita'
     di un gol nei 5 minuti x valore se arriva il gol) + (resto x valore se non arriva). La probabilita' nei
     5 minuti viene da quella dei 3 minuti. Vicino alla soglia: chiude se aspettare vale meno di chiudere
     adesso. Lontano dalla soglia: chiude se aspettare vale meno di (chiudere adesso - 1 % della base).
- Ordini di chiusura: vedi riquadro 10.

**Esempio con le cifre** (base 12,26 EUR: soglia fissa 0,61 EUR; minimo intelligente 0,25 EUR; «vicino alla
soglia» da 0,37 EUR):
- **Soglia fissa**, 40', 0-0. Miglior banca Under 3,5 = 1,25, miglior banca Over 4,5 = 15. Chiudere
  l'Under: banca 12,00 EUR a 1,25 -> +2,00 in ogni esito (netto +1,90). Chiudere l'Over: banca 0,99 EUR a
  15 -> circa -1,27. Netto circa **+0,63 EUR** >= 0,61: Mike propone il cash out.
  - Se approvi: incassi circa **+0,63 EUR** qualunque sia il risultato.
  - Se non approvi e la partita finisce: 0-3 gol **+2,49 EUR**, 4 gol **-12,26 EUR**, 5+ gol **+2,02 EUR**.
- **Intelligente, punteggio caldo**, 85', 2-1. Banca Under 3,5 = 1,20 (chiusura +2,50, netto +2,38), banca
  Over 4,5 = 60 (chiusura circa -2,01). Netto circa **+0,36 EUR**: sotto la soglia di 0,61, ma sopra il
  minimo di 0,25 e i gol sono 3 -> Mike propone di chiudere. Se approvi: +0,36 EUR in ogni caso. Se tieni:
  finisce 2-1 **+2,49 EUR**; arriva il 4o gol **-12,26 EUR**.
- **Intelligente, fase calda**, 30', 0-0, netto +0,45 EUR (fra 0,37 e 0,61) e probabilita' di gol nei 3
  minuti al 12 % -> Mike propone di chiudere a +0,45 EUR.

**Cosa vedi nell'app**: il riquadro ambra «Mike vorrebbe uscire» sotto la card, con il motivo («profit: 0.63 >=
5% di 12.26» oppure «profit smart: 0.36 (punteggio caldo ...)»), gli ordini proposti, il netto bloccabile e il
pulsante **Approva uscita**.

**Se qualcosa va storto**: se il netto scende sotto la soglia prima del tuo clic, la proposta decade da sola.
Se la tua firma resta non usata per 120 secondi, scade.

**Per il tecnico**: `engine.py:3527-3539`; soglia `should_cashout` 1004-1007; intelligente `smart_cashout`
1075-1132. Parametri (`config.py`): `cashout_profit_pct` 5,0 (229); `cashout_smart_enabled` True (244);
`cashout_smart_min_pct` 2,0 (255); `cashout_smart_tolerance_pct` 2,0 (256); `cashout_smart_hazard_hot` 0,10
(257); `cashout_smart_pressure_hot` 1,15 (258); `cashout_smart_goals_hot` 3 (259);
`cashout_smart_ev_margin_pct` 1,0 (260); `cover_wait_step_min` 5 (199). Motivo di chiusura «profit».

---

## 5. Uscita in perdita (riquadro rosa) - MANUALE

**Cosa fa**: all'intervallo e fra il 46' e l'85', se i gol sono 3 o 4, confronta «chiudo adesso e perdo una
cifra certa» con «tengo fino alla fine». Chiude quando chiudere vale almeno quanto tenere.

**Quando**: posizione coperta, prezzi completi, nessun cash out a profitto, e una finestra aperta:
1. E' l'intervallo e l'uscita all'intervallo e' accesa? -> finestra «HT» (perdita tollerata 25 %).
2. Altrimenti: il minuto e' noto ed e' fra 46 e 85 compresi, e l'uscita del secondo tempo e' accesa? ->
   finestra «2T» (perdita tollerata 25 %).
3. Altrimenti nessuna finestra: questo riquadro non fa niente.
Poi: i gol sono fra 3 e 4? Se no, niente. La stessa fascia di gol vale per l'intervallo e per il secondo tempo.

**Numeri**:
- **Modo «modello»** (di serie). Valore di tenere = somma, per ogni risultato finale possibile, di
  (probabilita' del risultato x guadagno o perdita con quel risultato). Le probabilita' sono la media fra
  modello e statistica storica; se mancano entrambe si usano quelle del mercato.
- Probabilita' dei 4 gol «prudente» (accesa): se il mercato da' ai 4 gol una probabilita' piu' alta, Mike
  usa quella del mercato.
- Premio al rischio = 10 % x probabilita' dei 4 gol x base.
- Mike chiude se: netto di adesso >= valore di tenere - premio.
- Se il modello dice di tenere, Mike tiene: la regola fissa non si usa.
- **Regola fissa** (solo se non c'e' nessun dato di probabilita', o se scegli il modo «fisso»): chiude se la
  perdita bloccabile e' al massimo il 25 % della base.
- Tetto opzionale del modello («perdita massima per uscire»): 0 = spento. Se lo accendi e la perdita e' oltre,
  il modello tiene.

**Esempio con le cifre** (base 12,26 EUR):
- **Modello**, intervallo sul 2-1. Banca Under 3,5 = 3,20 (chiusura circa -5,32), banca Over 4,5 = 3,40
  (chiusura circa +2,12, netto +2,01). Netto circa **-3,31 EUR**. Probabilita' del risultato finale (numeri
  scelti solo per mostrare il conto: quelle vere le calcola il modello partita per partita): 3 gol 30 %,
  4 gol 36 %, 5+ gol 34 %. Valore di tenere = 0,30 x 2,49 + 0,36 x (-12,26) + 0,34 x 2,02 = **-2,98**. Premio =
  10 % x 0,36 x 12,26 = 0,44. Soglia = -2,98 - 0,44 = **-3,42**. -3,31 e' sopra -3,42: Mike propone di chiudere.
  - Se approvi: perdi circa **-3,31 EUR** qualunque sia il risultato.
  - Se non approvi: finisce 2-1 **+2,49 EUR**; 4 gol **-12,26 EUR**; 5+ gol **+2,02 EUR**.
  - Con la regola fissa la stessa posizione NON si chiuderebbe: -3,31 e' oltre il 25 % della base (-3,07).
- **Regola fissa** (dati assenti), intervallo sul 2-1, netto -2,50 EUR (20 % della base) -> Mike propone di
  chiudere a -2,50 EUR.

**Cosa vedi nell'app**: la proposta in ROSSO («urgente») con il motivo «uscita a modello (ht): chiudere
(-3.31) vale piu' di tenere (-2.98 - premio 0.44, P4 36%)» oppure «loss tollerata (ht): -2.50 entro 25% di
12.26»; nell'attivita' la voce della decisione d'uscita in perdita, che resta nello storico.

**Se qualcosa va storto**: con 4 gol l'Under 3,5 e' gia' perso: Mike puo' chiudere solo l'Over 4,5.

**Per il tecnico**: finestra `_loss_rule` `engine.py:3501-3508`; decisione 3540-3578; `loss_exit_model`
1171-1209; `hold_expectation` 1146-1168; `loss_exit_ok` 1010-1015. Parametri (`config.py`):
`loss_exit_mode` «model» (267); `loss_exit_risk_premium_pct` 10 (278); `loss_exit_p4_prudent` True (279);
`loss_exit_max_pct` 0 (280); `ht_loss_exit_enabled` True (282); `ht_loss_pct` 25 (283); `ht_loss_goals_min` 3
(287); `ht_loss_goals_max` 4 (288); `h2_loss_exit_enabled` True (289); `h2_loss_pct` 25 (290); `h2_loss_from_min`
46 (291); `h2_loss_to_min` 85 (292). Motivo di chiusura «loss_ht» o «loss_2t»; telemetria `loss_exit_deciso`.

---

## 6. Tetto di perdita (riquadro rosa) - SEMPRE AUTOMATICO

**Cosa fa**: chiude tutto se la perdita bloccabile raggiunge una percentuale della base. E' una protezione:
parte da sola anche con le uscite manuali, senza chiederti la firma.

**Quando**: posizione coperta, prezzi completi, nessuna uscita dei riquadri 4 e 5, tetto maggiore di 0, base
maggiore di 0, e netto bloccabile <= -(base x tetto / 100).

**Numeri**: tetto di serie **100 %** della base (si puo' mettere fra 0 e 500; 0 = spento).

**Esempio con le cifre** (base 12,26 EUR): con il 100 % Mike chiude solo se il netto bloccabile e' -12,26 EUR o
peggio, cioe' quando non c'e' piu' niente da salvare. Esempio: 4 gol all'88', Under 3,5 perso (-10,00), Over
4,5 bancabile a 30 (chiusura circa -1,76): netto circa -11,76 -> il tetto NON scatta. Se mettessi il tetto al
50 % (-6,13), qui Mike chiuderebbe da solo: perdita fissata a circa **-11,76 EUR**; tenendo, con il 5o gol
avresti **+2,02 EUR**, senza **-12,26 EUR**.

**Cosa vedi nell'app**: «cap perdita evento: -11.76». Nessuna proposta: la chiusura parte.

**Se qualcosa va storto**: anche il tetto passa dai controlli d'ordine: con prezzi non vivi l'ordine non parte
(riquadro 10).

**Per il tecnico**: `engine.py:3579-3583`; `event_loss_cap_pct` 100 (`config.py:309`). Motivo «loss_cap»,
unico motivo in `MOTIVI_PROTEZIONE` (`engine.py:2229`), lasciato passare da `gate_uscite` (2361-2362).

---

## 7. Tengo (riquadro ambra, fine del percorso principale)

**Cosa fa**: nessuna uscita e' scattata. Mike tiene la posizione e al giro dopo rifa' tutti i controlli.
Unica eccezione: se sta aspettando la seconda tranche di copertura e il tempo e' passato, va al riquadro 8.

**Quando**: posizione coperta, nessuna uscita dei riquadri 4-6.

**Numeri**: nessuno.

**Esempio con le cifre**: 55', 1-0, netto -0,80 EUR, nessuna finestra di perdita con 1 gol: «tengo».

**Cosa vedi nell'app**: «tengo».

**Se qualcosa va storto**: niente di particolare.

**Per il tecnico**: `engine.py:3603`.

---

## 8. Seconda tranche (riquadro azzurro, fascia «Attese e ritorni») - SEMPRE AUTOMATICA

**Cosa fa**: dopo un gol precoce la copertura si compra in due meta'. Se la prima meta' e' abbinata e sono
passati 3 minuti, Mike torna a coprire il RESIDUO (capitolo 04), ricalcolato sulla quota dell'Over di quel
momento e su quanto la prima meta' ha gia' coperto.

**Quando**: posizione coperta, nessuna uscita, fase «attesa seconda tranche», e sono passati almeno 180
secondi dall'abbinamento della prima tranche (oppure l'ora della prima tranche non e' nota: allora subito).

**Numeri**: attesa 180 secondi.

**Esempio con le cifre**: prima tranche 1,35 EUR sull'Over 4,5 a 8,00 abbinata alle 21:07. Alle 21:10 l'Over
e' a 5,00: Mike torna a coprire e compra la seconda tranche, 2,37 EUR.

**Cosa vedi nell'app**: «seconda tranche: completo la copertura».

**Se qualcosa va storto**: le uscite dei riquadri 4-6 hanno la precedenza: se la posizione si chiude, la
seconda tranche non si compra.

**Per il tecnico**: `engine.py:3593-3602`; `early_goal_cover2_delay_s` 180 (`config.py:185`); porta a
`LIVE_UNCOVERED` con `cover_stage` 3 e `cover_forced` vero.

---

## 9. Proposta a te (riquadro grigio) - la tua firma

**Cosa fa**: con le uscite manuali (di serie) un cash out o un'uscita in perdita NON parte: Mike la scrive
come proposta e resta in posizione coperta. Quando approvi, al giro dopo Mike rifa' il calcolo sui prezzi di
quel momento e, se la strategia vuole ancora la STESSA uscita, manda gli ordini.

**Quando**: il riquadro 4 o 5 ha deciso di uscire e l'interruttore «uscite automatiche» e' spento.

**Numeri**:
- La firma vale **120 secondi**; poi scade e serve un nuovo clic.
- La firma si consuma all'uso.
- La firma vale solo per la stessa uscita: se il motivo cambia (esempio: da cash out in profitto a uscita in
  perdita) la firma cade e Mike propone quella nuova.
- Se la strategia non vuole piu' uscire, la proposta decade da sola.
- Il pulsante **Approva uscita** e' spento con prezzi non vivi o con un'altra richiesta in corso.

**Esempio con le cifre**: alle 21:40:10 Mike propone il cash out a +0,63 EUR. Approvi alle 21:40:40: al giro
dopo il netto e' +0,66, la strategia vuole ancora uscire in profitto -> partono le due banche (Under 3,5 e
Over 4,5). Se invece alle 21:40:30 il netto fosse sceso a +0,50, la proposta sarebbe decaduta e il clic
non avrebbe mandato niente.

**Cosa vedi nell'app**: il riquadro «Mike vorrebbe uscire» (ambra; rosso se in perdita) con motivo, ordini,
prezzi aggiornati, «chiudendo ora», «alla decisione», da quanti secondi e' stata decisa, minuto, pulsante.

**Se qualcosa va storto**: vedi «Punti da decidere», n. 3 (dopo la prima chiusura della partita, le uscite
successive dello stesso tipo possono partire senza nuova firma: da confermare).

**Paper o live**: identico. In live un'uscita approvata muove soldi veri.

**Per il tecnico**: `engine.gate_uscite` 2337-2431; `APPROVAZIONE_TTL_S` 120 (2240); `USCITE_DISCREZIONALI`
2225-2226; `_stessa_uscita_firmata` 2298-2310; `_decadi` 2317-2334; interruttore `uscite_automatiche` False
(`config.py:254`). Approvazione dal servizio: `_request_approva_uscita` (`service.py:3216`, area C scheda
58). UI: `PropostaUscitaMike.tsx` (area E scheda 44).

---

## 10. Chiusura in corso (riquadro azzurro) - i riprezzi sono SEMPRE AUTOMATICI

**Cosa fa**: manda e segue gli ordini che chiudono la posizione, selezione per selezione, al miglior prezzo;
ripresenta la chiusura del residuo non abbinato; quando non resta niente in gioco passa a Piatto. Una volta
partita la chiusura (approvata da te o automatica), i riprezzi non chiedono una seconda firma.

**Quando**: casella «chiusura in corso», dopo un'uscita dei riquadri 4, 5 o 6 (o una tua chiusura dalla UI).

**Gli ordini di chiusura** (uno per selezione ancora in gioco):
| Selezione | Ordine | Quota | Importo |
|---|---|---|---|
| Under 3,5 | banca | miglior banca | chiude tutta l'esposizione netta |
| Over 4,5 | banca | miglior banca | chiude tutta l'esposizione netta |
| Under 4,5 (rientro) | banca | miglior banca | chiude tutta l'esposizione netta |
Prima di ogni banca Mike ritira gli altri ordini vivi sulla stessa selezione. Una chiusura sotto 0,01 EUR
non si tenta.

**Controlli a ogni giro, nell'ordine**:
1. Una chiusura in attesa sta su una selezione gia' decisa dai gol? -> la ritira.
2. Nessuna chiusura in attesa: resta rischio in gioco e i tentativi sono meno di 20? -> ripresenta la
   chiusura del residuo al miglior prezzo (tentativi +1). Altrimenti -> **Piatto**; il rientro e' permesso
   SOLO se il motivo era il profitto.
3. Tentativi arrivati a 20 con una chiusura ancora in attesa? -> riquadro 12.
4. Una chiusura e' in attesa da almeno 10 secondi? -> la ritira e la rimanda al miglior prezzo per il
   residuo (tentativi +1).
5. Altrimenti aspetta.

**Numeri**: riprezzo dopo 10 secondi; massimo 20 tentativi; quota = miglior prezzo (0 tick di margine).

**Esempio con le cifre**: cash out approvato al 40'. Parte la banca Under 3,5 12,00 EUR a 1,25: si abbina.
Parte la banca Over 4,5 0,99 EUR a 15: non si abbina; al giro dopo la miglior banca e' 14,5 -> Mike ripresenta
1,03 EUR a 14,5, si abbina. Tutto chiuso: Piatto, rientro permesso, circa +0,63 EUR bloccati.

**Cosa vedi nell'app**: «chiusura residuo», «chiusura: riprezzo», «attesa fill chiusura», «chiusura su
selezione gia' decisa: annullo», poi «chiuso (profit)».

**Se qualcosa va storto**:
- **Con prezzi non vivi (feed fermo) non parte nessun ordine, chiusure comprese**, in paper e in live: la
  chiusura viene annullata prima di arrivare al mercato e Mike la ripresenta al giro dopo. Verificato sul
  codice del servizio (`service.py:709-717`).
- Mai due banche insieme sulla stessa selezione: il riprezzo parte in due giri (prima il ritiro confermato,
  poi la banca nuova).
- Ordine a esito ignoto: resta nel rischio, blocca le aperture, non le chiusure.

**Paper o live**: stessa logica. Le banche di chiusura su Under 3,5 e Over 4,5 partono «tutto o niente» e
cadono alla sospensione (area C, scheda 24). La banca sull'Under 4,5, se le green sono in modo appoggiato (di
serie), resta sul libro: vedi «Punti da decidere», n. 5.

**Per il tecnico**: stato `LIVE_CLOSING`, `engine.py:3606-3651` (1: 3610-3615; 2: 3616-3626; 3: 3628-3632;
4: 3633-3650; 5: 3651); ordini `_close_actions` 1754-1783 (ruoli `under_close`, `over_close`,
`reentry_green`); chiusure in attesa `_pending_closings` 1815-1816 (`under_close`, `over_close`,
`manual_close`); `size_chiudibile` 1717-1734; «mai due lay» `_una_sola_lay` 1901; `close_retry_s` 10 e
`close_max_attempts` 20 (`config.py:261-262`); `STATI_USCITA_IN_CORSO` 2234. Servizio: `execute_place`
`service.py:618-943`, freno «una sola chiusura in volo» 656-669, prezzi non vivi 709-717.

---

## 11. Piatto (riquadro ambra, fascia «Ordini di chiusura»)

**Cosa fa**: la chiusura e' finita: non resta rischio chiudibile. Da qui continua il capitolo 05b (residui,
rientro sull'Under 4,5, regolamento).

**Quando**: dal riquadro 10 (tutto chiuso, oppure 20 tentativi senza chiusure in attesa) o dal riquadro 2
(nessuna selezione in gioco).

**Numeri**: il rientro e' permesso solo se la chiusura era in profitto (motivo «profit»); tentativi azzerati.

**Esempio con le cifre**: cash out a +0,63 EUR al 40': Piatto con rientro permesso. Uscita in perdita a -3,31
EUR all'intervallo: Piatto senza rientro.

**Cosa vedi nell'app**: «chiuso (profit)», «chiuso (loss_ht)», «chiuso (loss_cap)».

**Se qualcosa va storto**: se in Piatto risulta ancora rischio chiudibile, Mike torna in posizione coperta
(capitolo 05b, riquadro «Torna alle uscite»).

**Per il tecnico**: `engine.py:3625-3626` (`reentry_allowed` = `close_reason == "profit"`).

---

## 12. Tentativi finiti (riquadro rosa, fascia «Blocco»)

**Cosa fa**: dopo 20 tentativi, con una chiusura ancora in attesa, Mike smette di riprezzare e resta fermo con
la chiusura sul libro. Lo scrive nell'attivita'.

**Quando**: casella «chiusura in corso», tentativi >= 20 e almeno una chiusura in attesa.

**Numeri**: 20 tentativi (parametro, 1-100). Il contatore dei tentativi e' lo stesso usato da green
pre-partita, seconda puntata e copertura.

**Esempio con le cifre**: la banca Over 4,5 da 0,99 EUR non si abbina per 20 riprezzi: resta sul libro. Se
non si abbina, la posizione arriva al regolamento con l'Over aperto (esiti della posizione d'esempio: +2,49 /
-12,26 / +2,02 EUR, meno quanto gia' chiuso sull'Under).

**Cosa vedi nell'app**: «chiusura: tentativi esauriti». Per uscire: **Flatten** o **Cash out** dalla scheda
della partita, oppure la fine del mercato.

**Se qualcosa va storto**: e' gia' il caso «storto»: serve il tuo intervento.

**Per il tecnico**: `engine.py:3628-3632`, telemetria `close_retries_exhausted`; contatore condiviso
`attempts` (inventario B, Cose strane 16).

---

## Frecce

- Posizione coperta -> Resta rischio?: a ogni giro (circa 0,5-2 secondi).
- Resta rischio? -> Cash out profitto («si'»): almeno una selezione aperta in gioco e tutti i prezzi presenti.
- Resta rischio? -> Prezzi incompleti («manca un prezzo»): una selezione in gioco senza miglior punta o
  miglior banca. Si resta in posizione coperta.
- Resta rischio? -> Piatto (freccia non disegnata, sta nella scheda 2): nessuna selezione aperta ancora in gioco.
- Cash out profitto -> Proposta a te («netto >= 5 %»): netto bloccabile >= 5 % della base, oppure una regola
  del cash out intelligente (netto >= 2 % della base e: 3+ gol, o fase calda vicino alla soglia, o valore di
  aspettare inferiore).
- Cash out profitto -> Uscita in perdita («no»): nessuna delle due regole.
- Uscita in perdita -> Proposta a te («chiudere conviene»): intervallo o minuto 46-85, 3 o 4 gol, e modello
  (netto >= valore di tenere - premio) oppure, senza dati, perdita entro il 25 % della base.
- Uscita in perdita -> Tetto perdita («no»): nessuna finestra, gol fuori da 3-4, o il modello dice di tenere.
- Tetto perdita -> Chiusura in corso («sempre»): netto <= -100 % della base. Nessuna firma.
- Tetto perdita -> Tengo («no»): netto sopra il tetto.
- Tengo -> Seconda tranche («180 s dalla 1a»): fase «attesa seconda tranche» e 180 secondi dall'abbinamento
  della prima tranche (o ora della prima tranche sconosciuta).
- Proposta a te -> Chiusura in corso («approvi»): firma entro 120 secondi e stessa uscita ancora voluta.
  Con l'interruttore «uscite automatiche» acceso questa tappa non esiste: si va diretti alla chiusura.
- Chiusura in corso -> Piatto («tutto chiuso»): nessuna chiusura in attesa e nessun rischio in gioco, oppure
  20 tentativi e nessuna chiusura in attesa.
- Chiusura in corso -> Tentativi finiti («20 tentativi»): 20 tentativi con una chiusura ancora in attesa.
- Da ogni riquadro -> Regolamento (capitolo 05b): mercato chiuso.

---

## Punti da decidere

1. **Prezzi non vivi = nessun ordine, chiusure comprese** (area C, Differenze 5; verificato sul codice,
   `service.py:709-717` e, per le banche appoggiate, `service.py:4462-4477`). La Costituzione (§5) dice
   «chiusure permesse». Oggi con il feed fermo non partono ne' cash out, ne' uscite in perdita, ne' il tetto di
   perdita. Scelta dell'utente del 28/09: confermare che vale anche per il tetto di perdita.
2. **Tetto di perdita al 100 %** (inventario B, Cose strane 15): chiude solo quando non c'e' piu' niente da
   salvare. Di fatto e' spento. Decidere se abbassarlo.
3. **Uscite successive senza nuova firma** (da confermare: letto sul codice, non provato col replay). Mike
   considera «gia' in corso» un'uscita se nella partita esiste gia' un ordine dello stesso tipo nello stesso
   ciclo, anche ritirato (`engine.py:2269-2285`). In gioco il ciclo non cambia: dopo il primo cash out approvato
   (anche abbinato solo in parte), un'uscita in perdita successiva con banca sull'Under 3,5 o sull'Over 4,5
   potrebbe partire senza chiederti la firma.
4. **Riprezzo della chiusura** (da confermare col replay; inventario B, Cose strane 3). Il ritiro e la banca
   nuova non partono nello stesso giro («mai due lay»): il riprezzo si completa al giro dopo come «chiusura
   residuo», e ogni riprezzo consuma 2 tentativi su 20. In piu', le banche di chiusura partono «tutto o
   niente»: se non si abbinano sono annullate subito e non restano «in attesa» per 10 secondi. Con il feed fermo
   (punto 1) ogni giro consuma un tentativo; finiti i 20 tentativi senza chiusure in attesa Mike va a Piatto e,
   al giro dopo, torna in posizione coperta.
5. **Chiusura dell'Under 4,5 del rientro nel cash out** (verificato: `service.py:1330-1346`). Il cash out chiude
   l'Under 4,5 con lo stesso tipo d'ordine della green del rientro; con le green in modo «appoggiato» (di serie)
   questa banca resta sul libro invece di partire «tutto o niente». Inoltre non e' contata fra le «chiusure in
   attesa» (inventario B, Cose strane 4): rischio di chiusura ripresentata mentre la vecchia e' ancora viva, poi
   bloccata da «mai due lay». Da verificare col replay.
6. **Fascia di gol 3-4 anche nel secondo tempo** (inventario B, Differenze 5): la Costituzione §3 Fase 5 dice «2,
   3 o 4 gol»; il codice parte dal terzo gol per l'intervallo e per il secondo tempo.
7. **Con prezzi incompleti nessuna uscita e' valutata**, tetto compreso (riquadro 3). Decidere se il tetto debba
   restare attivo anche con un prezzo mancante.
8. **Fra l'85' e la fine** e **fra il 1' e il 45'** non c'e' nessuna uscita in perdita: solo cash out a profitto e
   tetto.

## Punti non chiariti

- Le cifre degli esempi con chiusure sono arrotondate al centesimo a mano (l'arrotondamento esatto
  dell'importo di banca lo fa `compute_greenup`, non riletto riga per riga).
- Le probabilita' degli esempi (30 % / 36 % / 34 %, 12 %) sono inventate per mostrare il calcolo; le vere
  arrivano dal servizio (modello, statistica storica, mercato) e non le ho lette.
- Non ho letto come il servizio calcola «intervallo in corso», probabilita' di gol nei 3 minuti e pressione.
