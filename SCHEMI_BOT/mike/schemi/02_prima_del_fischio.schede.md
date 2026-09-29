# Mike - Schema 02: prima del fischio (schede)

Schema: `02_prima_del_fischio.html` (specifica `02_prima_del_fischio.workflow.json`).
Fonte dei fatti: `SCHEMI_BOT/mike/inventario/B_strategia.md`.
Schede dell'inventario usate qui: **1-21 tutte** (1 -> «13 controlli»; 2, 3, 4 -> «Veto Under 3,5»; 5, 18 -> «Fischio»;
6, 7 -> «Punta Under 3,5»; 8 -> «Osserva»; 9, 12, 20 -> «Giro chiuso»; 10, 15 -> «Chiusura finale»; 11, 16 -> «10' dal
fischio»; 13, 14, 19 -> «Banca appoggiata»; 17, 21 -> «Ultimo ingresso»), piu' la parte pre-partita della tabella
delle transizioni (righe da «qualunque pre-partita» a «PRE_LAST_ENTRY_PENDING»), il glossario, le differenze 1-4 e 10
dalla Costituzione e le cose strane 1, 2, 3, 5, 8, 11, 12, 13, 14.

**Colori (uguali in tutti gli schemi di Mike):** ambra = attesa; azzurro = azione, cioe' un ordine;
viola = decisione; verde = profitto bloccato; rosa = perdita o blocco; grigio = fermo o fine.

**Uscite manuali di serie.** Ogni bancata per uscire (bancata appoggiata, bancata al mercato, chiusura finale,
chiusura in perdita del veto) di serie NON parte da sola: diventa una proposta che approvi tu. Il ritiro degli
ordini d'ingresso resta automatico.

**Tick di Betfair negli esempi:** 0,01 sotto quota 2,00; 0,02 fra 2 e 3.

**Tutti i numeri sono i valori di serie**, modificabili dalla schermata dei parametri entro i limiti scritti fra
parentesi.

---

## 1. Osserva

**Cosa fa.** Mike guarda la partita senza posizione aperta nel giro. A ogni giro di controllo (circa ogni mezzo
secondo) prova i 13 controlli d'ingresso.

**Quando.** All'inizio, dopo un giro chiuso, dopo una punta non abbinata, e se la posizione pre-partita risulta
sparita.

**Numeri.** Nessuno proprio: quelli dei controlli (scheda 2).

**Esempio con le cifre.** Alle 20:00 (fischio 21:00) Mike e' qui con 0 giri fatti. La punta del giro 1 non si
abbina: Mike torna qui e al giro di controllo dopo puo' ripuntare subito, senza pausa.

**Cosa vedi nell'app.** Il motivo dell'attesa (vedi scheda 2) oppure «posizione assente», «ingresso non abbinato»,
«gamba assente».

**Se qualcosa va storto.** Posizione sparita mentre la bancata era sul book (per esempio una punta annullata dalla
riconciliazione): Mike ritira ogni ordine vivo e torna qui con «posizione assente».

**Per il tecnico.** Casella `WATCH`. Posizione sparita: `engine.py:2694-2695` (`PRE_OPEN`, somma Under <= 0).
Ritorno senza pausa dopo punta non abbinata: 2680-2681 (cose strane n. 5).

---

## 2. 13 controlli

**Cosa fa.** Prima di ogni punta pre-partita Mike si fa 13 domande, sempre in questo ordine. Al primo «no» non
punta, scrive il motivo e riprova al giro di controllo dopo.

**Quando.** In «Osserva», a ogni giro di controllo, finche' la partita non e' in gioco.

**Numeri e ordine esatto (raggruppati per tema).**

*Blocchi decisi da te*
1. La partita e' stata chiusa a mano da te? Se si': «rientro disabilitato (chiusura manuale): premi Riprendi».
2. C'e' una tua chiusura manuale in corso? Se si': «chiusura manuale in corso».
3. Il pre-partita e' spento? Se si': «pre_disabilitato». (A bot fermo il pre-partita e' sempre spento.)

*Dati freschi*
4. I dati sono abbastanza freschi per mandare un ordine? Il prezzo non deve avere piu' di 20 secondi e l'elenco
   partite piu' di 30 secondi. Se no: «feed stantio».

*Orario e giri*
5. Manca piu' di 1,0 ora al fischio (limiti 0,25-12 ore)? Se si': «fuori finestra».
6. Mancano 10 minuti o meno al fischio (limiti 1-120)? Se si': «finestra pre-match chiusa».
7. Mike ha gia' fatto 10 giri (limiti 0-100)? Se si': «max cicli».
8. Sono passati meno di 60 secondi dall'ultimo giro chiuso (limiti 0-3600)? Se si': «cooldown».

*Mercato e quota*
9. Manca il mercato Under 3,5, o la quota di punta non e' valida, o il mercato non e' aperto, o risulta gia' in
   gioco? Se si': «book assente».
10. La quota di punta dell'Under 3,5 e' fuori da 1,30-3,00? Se si': «prezzo X fuori banda».
11. Al miglior prezzo di punta ci sono meno di 10 euro disponibili (10 euro x fattore 1,0; fattore 0,5-5)? Se si':
    «liquidita X < Y».
12. Se c'e' una quota di bancata: la distanza fra miglior punta e miglior bancata e' piu' di 6 tick (limiti 1-20),
    o non si puo' calcolare? Se si': «spread N tick».

*Tetto di rischio*
13. I 10 euro superano lo spazio rimasto sotto il tetto di rischio della partita? Di serie il tetto e' 0 = spento.
    Se si': «cap liability partita».

**Esempio con le cifre.** Fischio 21:00, sono le 20:30. Under 3,5: punta 1,50 con 42 euro disponibili, bancata
1,52 (2 tick). Giri fatti 2, ultimo giro chiuso alle 20:28. Tutte e 13 le risposte sono «va bene»: Mike punta.
Alle 20:51 la risposta 6 e' «si'»: non punta piu'. Alle 19:45 la risposta 5 e' «si'»: non punta ancora.

**Cosa vedi nell'app.** Il motivo del primo «no», fra virgolette come sopra, nella scheda della partita e
nell'attivita'.

**Se qualcosa va storto.** Se i dati si fermano Mike non punta («feed stantio») ma non ritira nulla da qui.

**Paper o live.** Identico.

**Per il tecnico.** `_entry_guard` `engine.py:2495-2538` (1: 2497; 2: 2500; 3: 2502; 4: 2504; 5: 2512-2514; 6: 2515;
7: 2517; 8: 2519; 9: 2521-2523; 10: 2524; 11: 2526-2528; 12: 2532-2535; 13: 2536). Chiavi `no_reentry`,
`flatten_pending`, `pre_enabled`, `snap.order_fresh` (`order_max_age_s` 20, `order_scanner_max_s` 30),
`entry_hours_before_ko`, `pre_last_entry_min`, `pre_max_cycles`, `pre_reentry_cooldown_s`, `pre_entry_price_min/max`,
`pre_min_back_size_factor`, `stake`, `pre_max_spread_ticks`, `max_liability_per_match` (`liability_room` 1707).
A bot fermo `service.py:1273` forza `pre_enabled` = False.

---

## 3. Punta Under 3,5

**Cosa fa.** Mike punta 10 euro sull'Under 3,5 al miglior prezzo di punta di adesso e aspetta che si abbini.

**Quando.** Appena i 13 controlli sono tutti «va bene».

**Numeri.** Importo 10,00 euro (limiti 0,50-500). Quota = miglior punta, arrotondata alla scala Betfair.
Attesa massima 60 secondi (limiti 5-3600). L'ordine cade al fischio se non abbinato.

**Esempio con le cifre.** Alle 20:30:00 Mike punta 10,00 euro a 1,50. Tre casi:
- abbinata per intero -> «Banca appoggiata». Con 0-3 gol vinci +5,00 euro, con 4+ gol perdi 10,00 euro (prima della bancata);
- alle 20:31:00 abbinati 4,00 euro su 10 -> Mike ritira i 6,00 euro restanti e tiene 4,00 euro a 1,50;
- alle 20:31:00 niente abbinato -> Mike ritira e torna a «Osserva», senza contare il giro.

**Cosa vedi nell'app.** «ingresso ciclo 1», «attesa fill ingresso», «ttl: tengo la parte abbinata», «ttl scaduto»,
«ingresso non abbinato».

**Se qualcosa va storto.** Punta rifiutata dal mercato o ritirata: torna a «Osserva» e puo' ripuntare subito (niente
freno sui rifiuti ripetuti, vedi «Punti da decidere»).

**Paper o live.** Da confermare: l'ordine vero parte «tutto o niente» in paper e in live, quindi o si abbina subito
per intero o muore. L'attesa di 60 secondi e il «tengo la parte abbinata» in pratica non hanno oggetto (vedi
«Punti da decidere» n. 2).

**Per il tecnico.** Ingresso `engine.py:2668-2674` (ruolo `under_entry`, LAPSE, casella `PRE_ENTRY_PENDING`, «ingresso
ciclo N»). Attesa 2676-2691 (gamba assente 2678; morta senza abbinato 2680; abbinata 2682; scadenza `pre_entry_ttl_s`
2684-2688; piena ma viva 2689; attesa 2691). Il prezzo del primo ingresso della partita NON si scrive quando si tiene
una parte per scadenza (cose strane n. 11): si scrive al fischio.

---

## 4. Banca appoggiata

**Cosa fa.** Appena la punta e' abbinata Mike ricorda il prezzo del primo ingresso della partita e appoggia sul
book una bancata 2 tick sotto il prezzo medio, per tutta l'esposizione. Se la bancata sparisce (ritirata, o
abbinata in parte e poi ritirata) ne rimette una per il residuo.

**Quando.** Posizione aperta prima dei 10 minuti finali.

**Numeri.** 2 tick sotto (limiti 1-10). Importo = esposizione netta / quota. Cade al fischio se non abbinata.
Modo di serie «appoggiata» (l'altro modo e' «al mercato»).

**Esempio con le cifre.** Punta 10,00 a 1,50 abbinata: bancata 10,14 euro a 1,48. Se si abbina, +0,13 / +0,14 euro
lordi (scheda 5). Caso residuo: la bancata si abbina per 4,00 euro e poi viene ritirata. Esposizione: con 0-3 gol
+5,00 - 4,00 x 0,48 = +3,08; con 4+ gol -10,00 + 4,00 = -6,00. Nuova bancata (3,08 + 6,00) / 1,48 = 6,14 euro a 1,48.

**Modo «al mercato».** Mike non appoggia niente: aspetta che la miglior bancata scenda a 2 tick sotto il prezzo medio
e allora banca al miglior prezzo per tutta l'esposizione. Esempio: punta 10,00 a 1,50, miglior bancata 1,48 -> banca
10,14 euro a 1,48. Mentre aspetta scrive «posizione aperta, in attesa dei 2 tick».

**Cosa vedi nell'app.** «ingresso abbinato», «green resting appoggiata», «green resting appoggiata (residuo)»,
«posizione aperta, green resting sul book», «green taker: 2 tick disponibili». Con le uscite manuali la bancata e'
una proposta.

**Se qualcosa va storto.** Se la stessa identica bancata era gia' stata rifiutata dal mercato Mike non la ripete
(«gia' rifiutata a mercato ... non si ripropone identica»). Nel modo «al mercato» la bancata viene riprezzata ogni 10
secondi fino a 20 volte (ma vedi «Punti da decidere» n. 5).

**Paper o live.** In live, se spegni l'interruttore «bancata appoggiata in live» (di serie acceso), Mike usa il modo
«al mercato».

**Per il tecnico.** `_after_entry_fill` `engine.py:2819-2832` (nota «take-profit resting», `entry_price_initial`).
Resting 2747-2761 (`tentativo_gia_rifiutato` 1522); taker 2762-2777. Ruolo `under_green`. Parametri `pre_exit_mode`
«resting», `pre_green_ticks` 2. Ripiego live `service.py:1262-1264` (`live_resting_enabled`). Il servizio tratta
`under_green` come appoggiata solo in modo resting (`service.py:1345-1346`).

---

## 5. Giro chiuso

**Cosa fa.** Quando la bancata si abbina per intero e la posizione e' piatta, Mike chiude il giro: ritira gli ordini
ancora vivi, conta il giro, segna l'ora (parte la pausa), archivia le puntate del giro e torna a «Osserva».

**Quando.** Tre casi: bancata appoggiata abbinata prima dei 10 minuti finali; bancata al mercato abbinata; posizione
gia' piatta proprio a 10 minuti dal fischio.

**Numeri.** Pausa 60 secondi prima del giro dopo. Piatto = differenza fra i due esiti sotto 0,01 euro. Il profitto
mostrato e' lordo (senza commissione).

**Esempio con le cifre.** Punta 10,00 a 1,50 e bancata 10,14 a 1,48 abbinate: «ciclo 1 chiuso: +0.14». Con 0-3 gol
+5,00 - 4,87 = +0,13 euro; con 4+ gol -10,00 + 10,14 = +0,14 euro. Se succede alle 20:50:05, cioe' gia' dentro gli
ultimi 10 minuti, il giro si chiude ma Mike non puo' piu' puntare: al fischio e' senza posizione e non fa l'ultimo
ingresso.

**Cosa vedi nell'app.** «ciclo N chiuso: +X» e la riga del giro nello storico (ciclo, entrata, uscita, importo,
profitto).

**Se qualcosa va storto.** Le puntate archiviate restano nel conto finale ma non contano piu' come rischio. Quelle
ancora vive o a esito ignoto non vengono archiviate.

**Per il tecnico.** `_cycle_done` `engine.py:2835-2855` (`cycle_no` +1, `last_green_at`, `attempts` 0,
`_archive_legs`). Piatto a 10': 2702-2705. Piatto prima dei 10': 2745-2746. Archiviazione `apply_decision`
3827-3849. Costante `_FLAT_EPS` 0,01. Profitto = vincita lorda dell'esposizione (2839-2840), non netto (cose strane n. 13).

---

## 6. 10' dal fischio

**Cosa fa.** A 10 minuti dal fischio, con una posizione aperta, Mike ritira la bancata appoggiata e fa l'ultima
scelta del pre-partita. Si chiede: chiudere adesso al miglior prezzo di bancata blocca un profitto?
- **Gia' piatta** -> «Giro chiuso» (niente ultimo ingresso).
- **Si', piu' di 0,01 euro** -> «Chiusura finale».
- **No** e veto spento, o il veto dice «va bene», o il veto non si puo' valutare -> **tengo**: Mike porta la
  posizione in gioco cosi' com'e' e aspetta il fischio.
- **No** e il veto dice «sotto soglia» -> «Veto Under 3,5».
- **Manca la quota di bancata** (o il mercato) -> tengo, anche se il veto direbbe di chiudere: senza prezzo non si
  puo' chiudere.

**Quando.** Da 10 minuti prima del fischio (limiti 1-120) al fischio, se c'e' una posizione aperta.

**Numeri.** Soglia di profitto 0,01 euro. Tenere = nessun ordine: la posizione in perdita resta aperta fino al
fischio, poi vale l'uscita al fischio (schema 01).

**Esempio con le cifre.** Punta 10,00 a 1,50.
- Miglior bancata 1,46: chiudere blocca +0,27 euro -> chiusura finale.
- Punta 1,60 / bancata 1,62: chiudere costa una bancata di 15,00 / 1,62 = 9,26 euro. Con 0-3 gol +5,00 - 9,26 x
  0,62 = -0,74; con 4+ gol -10,00 + 9,26 = -0,74. Perdita -0,74 euro: niente profitto. Con probabilita' calibrata
  0,70 (sopra la soglia 0,650) Mike tiene fino al fischio.

**Cosa vedi nell'app.** «ultimo ingresso: locked X > 0», «ultimo ingresso: locked X <= 0, tengo», «ultimo ingresso:
prezzo lay assente, tengo», «in perdita pre-KO: tengo fino al live»; il verbale del veto quando e' acceso.

**Se qualcosa va storto.** Mentre tiene, Mike non fa nulla fino al fischio: nessuna bancata, nessuna copertura.

**Paper o live.** Identico.

**Per il tecnico.** `engine.py:2702-2743` (piatto 2702-2705; prezzo assente 2706-2713; profitto 2714-2721; perdita e
veto 2722-2743). Tenere = casella `HOLD`, `engine.py:2810-2811`. `compute_greenup` (`greenup.py:118-210`) sul miglior
punta/bancata, profitto = minore dei due esiti, lordo.

---

## 7. Chiusura finale

**Cosa fa.** Chiude tutta la posizione con una bancata al miglior prezzo di bancata. Se si abbina, il giro e' chiuso
in profitto e Mike passa all'ultimo ingresso.

**Quando.** A 10 minuti dal fischio, quando chiudere adesso blocca piu' di 0,01 euro.

**Numeri.** Importo = (vincita - perdita) / quota. Cade al fischio se non abbinata. Riprezzo dopo 10 secondi
(limiti 1-600), massimo 20 tentativi (limiti 1-100).

**Esempio con le cifre.** Punta 10,00 a 1,50; miglior bancata 1,46: bancata 15,00 / 1,46 = 10,27 euro a 1,46. Con
0-3 gol +5,00 - 10,27 x 0,46 = +0,28; con 4+ gol -10,00 + 10,27 = +0,27. Profitto bloccato circa +0,27 euro lordi.
Se dopo 10 secondi non e' abbinata e la miglior bancata e' 1,47, Mike la ritira e ne manda una da 10,20 euro a 1,47.

**Cosa vedi nell'app.** «ultimo ingresso: locked 0.27 > 0», «green taker: riprezzo», «attesa fill green»; la voce del
profitto bloccato. Con le uscite manuali e' una proposta.

**Se qualcosa va storto.**
- Bancata morta senza abbinamento, o abbinata solo in parte: Mike **tiene** la posizione (o il residuo) fino al
  fischio e non fa l'ultimo ingresso.
- Riprezzo: per la regola «mai due bancate a mercato» la bancata nuova viene rimandata; al giro dopo la vecchia
  risulta ritirata senza abbinamento e Mike passa a «tengo». In pratica il riprezzo non avviene (da confermare col
  replay, «Punti da decidere» n. 5).
- Se la vecchia bancata appoggiata e' ancora viva, la chiusura finale parte al giro di controllo dopo.

**Per il tecnico.** Ordine `engine.py:2714-2721` (ruolo `under_green`, `final` = vero, LAPSE, nota «ultimo ingresso:
chiusura in profitto», casella `PRE_GREEN_PENDING`). Attesa 2779-2808 (assente 2781; morta 2783-2786 -> `HOLD` se
finale; parziale 2787-2796; abbinata 2797 -> `_after_final_green`; riprezzo `close_retry_s`/`close_max_attempts`
2804-2807; attesa 2808). Cose strane n. 3. Stessa casella usata dalla bancata «al mercato» del giro (non finale:
morta -> torna a «Banca appoggiata»; abbinata -> «Giro chiuso»).

---

## 8. Ultimo ingresso

**Cosa fa.** Dopo la chiusura finale abbinata Mike conta il giro chiuso e punta di nuovo 10 euro sull'Under 3,5,
cosi' la partita entra in gioco con una posizione fresca. Sulla carta e' l'unico ordine che resta valido in gioco.
Poi aspetta il fischio.

**Quando.** Chiusura finale abbinata per intero, posizione piatta. Mike si chiede, nell'ordine:
1. L'ultimo ingresso e' spento? Se si': niente, «ultimo ingresso disabilitato» -> fischio senza posizione.
2. Il veto e' gia' scattato su questa partita? Se si': niente, «non si rientra dopo il veto».
3. Il mercato e' sospeso? Se si': aspetta, «ultimo ingresso: mercato sospeso, aspetto».
4. Manca il mercato, o la quota non e' valida, o il mercato non e' aperto? Se si': niente, «ultimo ingresso: book assente».
5. Al miglior prezzo di punta ci sono meno di 10 euro? Se si': niente.
6. I 10 euro superano il tetto di rischio della partita (di serie spento)? Se si': niente, «cap liability partita».
7. Quota = miglior punta + 0 tick (limiti 0-3).
8. Veto acceso e, a questa quota, probabilita' sotto soglia? Se si': niente, «non rientro», veto ricordato.
9. Altrimenti punta 10 euro, «ultimo ingresso PERSIST», e aspetta il fischio («attesa fill ingresso PERSIST»).

**Numeri.** 10,00 euro. Quota miglior punta + 0 tick. Liquidita' minima 10 euro. Grazia di 120 secondi dopo il
fischio di calendario (limiti 0-900) prima di ritirare il residuo non abbinato.

**Esempio con le cifre.** Chiusura finale abbinata alle 20:50:20 con +0,27 euro. Miglior punta 1,45 con 30 euro
disponibili: Mike punta 10,00 euro a 1,45. Con 0-3 gol +4,50 euro, con 4+ gol -10,00 euro, prima dell'uscita al
fischio.

**Cosa vedi nell'app.** I motivi sopra. Se Mike non rientra, la partita in gioco mostra «LIVE · NESSUNA POSIZIONE».

**Se qualcosa va storto.** Punto da decidere n. 1: se al fischio l'ultimo ingresso non ha abbinato niente, Mike
passa a «senza posizione» senza ritirarlo e poi non lo ritira piu'.

**Paper o live.** **Da confermare**: sulla carta «resta valido in gioco», ma l'ordine vero parte «cade al fischio» e
«tutto o niente» sia in paper sia in live (righe citate in «Punti da decidere» n. 2). In pratica o si abbina subito per
intero o muore subito: non resta sul book fino al fischio. A bot fermo l'ultimo ingresso e' spento.

**Per il tecnico.** `_after_final_green` `engine.py:2858-2908` (1: 2861; 2: 2863; 3: 2873-2875; 4: 2876; 5: 2878-2880;
6: 2883-2885; 7: 2886-2889; 8: 2890-2898; 9: 2899-2908). Ruolo `under_last`, persistenza PERSIST (2901-2902),
casella `PRE_LAST_ENTRY_PENDING` (attesa 2813-2814). Parametri `last_entry_persist`, `last_entry_ticks_above`.
Tetto confrontato col tetto intero, non con lo spazio residuo (cose strane n. 8). A bot fermo `service.py:1275`.

---

## 9. Veto Under 3,5

**Cosa fa.** Il veto confronta la probabilita' che la partita finisca con 0-3 gol (calcolata dal dossier
pre-partita) con una soglia che dipende dalla quota. Se la probabilita' e' sotto soglia, a 10 minuti dal fischio
Mike **chiude in perdita** invece di tenere, e poi non fa l'ultimo ingresso.

**Quando.** Solo in due momenti: a 10 minuti dal fischio con posizione in perdita, e prima dell'ultimo ingresso.
Di serie e' ACCESO.

**Numeri.** Soglie per quota (modificabili): 1,30 -> 0,807; 1,50 -> 0,684; 2,00 -> 0,514; 2,50 -> 0,385; 3,00 ->
0,275. Fra due quote la soglia si calcola in linea retta; sotto 1,30 vale 0,807, sopra 3,00 vale 0,275. Tre esiti:
«veto» (sotto soglia), «nessun veto» (uguale o sopra), «non valutabile» (manca la probabilita' o la quota: nessun veto).

**Esempio con le cifre.**
- Soglia a quota 1,40: 0,807 + (0,684 - 0,807) x 0,10 / 0,20 = 0,746.
- Punta 10,00 a 1,50; adesso punta 1,60 / bancata 1,62. Soglia a 1,60: 0,684 + (0,514 - 0,684) x 0,10 / 0,50 = 0,650.
  Probabilita' 0,62: veto. Mike banca 9,26 euro a 1,62 e blocca -0,74 euro in entrambi gli esiti. Al fischio e' senza
  posizione. Con probabilita' 0,70: nessun veto, tiene.

**Cosa vedi nell'app.** Nell'attivita' la voce del veto con momento, probabilita', quota, soglia, esito, motivo
(«P calibrata 0.620 < soglia 0.650 a quota 1.60») e se e' stato eseguito. Nota dell'ordine: «veto P calibrata Under
3.5: chiusura in perdita». Con le uscite manuali la chiusura e' una proposta.

**Se qualcosa va storto.**
- Il veto viene «ricordato» sulla partita anche se tu non approvi la proposta: la posizione entra in gioco e
  l'ultimo ingresso resta vietato.
- Chiusura in perdita non abbinata: Mike tiene fino al fischio.
- Se la chiave del veto manca dai parametri vale ACCESO; se c'e' ma non e' un vero/falso vale SPENTO.

**Paper o live.** Identico.

**Per il tecnico.** `veto_u35_acceso` `engine.py:2570-2577`; nodi `VETO_U35_NODI` 2560-2566 (`veto_p_under35_soglia_130`
... `_300`, `config.py:153-157`); `soglia_veto_under35` 2580-2598; `valuta_veto_under35` 2601-2625; chiusura
2722-2739 (ruolo `under_green`, `final`, casella `PRE_GREEN_PENDING`, verbale `veto_u35`). Probabilita'
`snap.p_under35_cal` (`service.py:290`, 4250). Commenti che lo dicono spento: 2542, 352 (cose strane n. 2).

---

## 10. Fischio

**Cosa fa.** Appena la partita risulta in gioco, qualunque cosa Mike stesse facendo prima del fischio, ritira gli
ordini non abbinati e decide come entra in gioco. Con una posizione Under 3,5 salva il prezzo al fischio, l'ora in
cui ha visto il gioco (da qui partono i 3 minuti dell'uscita) e i gol al fischio.
- Con posizione e uscita al fischio accesa -> uscita al fischio (schema 01).
- Con posizione e uscita al fischio spenta -> copertura Over 4,5 subito (schema 01).
- Senza posizione -> senza posizione in gioco (schema 01).

**Quando.** Primo controllo di ogni giro prima del fischio: vale da «Osserva», dalla punta in attesa, dalla
posizione aperta, dalla chiusura in attesa, dal «tengo» e dall'ultimo ingresso.

**Numeri.** L'ultimo ingresso non abbinato NON viene ritirato nei primi 120 secondi dal fischio di calendario.

**Esempio con le cifre.** Posizione 10,00 euro a 1,50; Mike vede il gioco alle 21:00:40 con 0-0: ora di gioco
21:00:40, gol al fischio 0, passa all'uscita al fischio con una bancata a 1,48.

**Cosa vedi nell'app.** «in gioco: provo l'uscita a +2 tick», «in-play con posizione Under», «in-play senza posizione»;
la fase della scheda passa in gioco.

**Se qualcosa va storto.** Una casella pre-partita sconosciuta (dato rovinato) porta a «DA SISTEMARE» con tutti gli
ordini ritirati: in pratica non puo' accadere.

**Per il tecnico.** `engine.py:2636-2666` (grazia 2641-2643; prezzo al fischio 2650-2651; `live_since` 2656-2659;
`LIVE_KO_GREEN` 2660-2663; `LIVE_UNCOVERED` con `cover_forced` 2664-2665; `IDLE_LIVE` 2666). Casella sconosciuta ->
`ERROR` 2816, irraggiungibile (`_dispatch` 2462-2464).

---

## Frecce

- Osserva -> 13 controlli: a ogni giro di controllo (circa ogni 0,5 secondi).
- 13 controlli -> Punta Under 3,5: tutte e 13 le risposte «va bene».
- 13 controlli -> Osserva («un no»): una risposta «no»; Mike scrive il motivo e riprova.
- Punta Under 3,5 -> Banca appoggiata: abbinata per intero (oppure dopo 60 secondi con una parte abbinata: tiene la parte).
- Punta Under 3,5 -> Osserva («niente in 60 s»): 60 secondi senza abbinamento, oppure ordine ritirato o rifiutato
  senza abbinamento. Nessuna pausa, giro non contato.
- Banca appoggiata -> Giro chiuso: bancata abbinata per intero e posizione piatta, prima dei 10 minuti finali.
- Giro chiuso -> Osserva: subito; la pausa di 60 secondi la fa rispettare il controllo n. 8.
- Banca appoggiata -> 10' dal fischio: mancano 10 minuti o meno al fischio.
- 10' dal fischio -> Chiusura finale: chiudere al miglior prezzo di bancata blocca piu' di 0,01 euro.
- 10' dal fischio -> Fischio («in perdita: tengo»): profitto bloccabile 0,01 euro o meno e nessun veto (spento,
  «nessun veto», «non valutabile»), oppure manca la quota di bancata.
- 10' dal fischio -> Giro chiuso (non disegnata): posizione gia' piatta.
- 10' dal fischio -> Veto Under 3,5: profitto bloccabile 0,01 euro o meno, veto acceso, probabilita' sotto soglia,
  quota di bancata presente.
- Chiusura finale -> Ultimo ingresso: chiusura finale abbinata per intero, posizione piatta.
- Chiusura finale -> Fischio (non disegnata): chiusura finale morta o abbinata in parte: Mike tiene fino al fischio.
- Ultimo ingresso -> Fischio: la punta e' piazzata (o non e' stata fatta per uno dei motivi 1-8).
- Veto Under 3,5 -> Fischio: chiusura in perdita abbinata, giro contato, niente ultimo ingresso: fischio senza posizione.
  Se la chiusura non si abbina: tiene fino al fischio.

## Punti da decidere

1. **Ultimo ingresso lasciato vivo senza posizione (da confermare).** Se al fischio l'ultimo ingresso non ha
   abbinato niente e i giri precedenti sono archiviati, Mike passa a «senza posizione» senza ritirarlo
   (`engine.py:2641-2643`, 2666) e in quella casella non lo ritira piu'. Sulla carta un abbinamento successivo
   lascerebbe una posizione Under 3,5 senza uscita e senza copertura.
2. **L'ultimo ingresso «resta valido in gioco» solo sulla carta (da confermare).** L'ordine vero parte con
   persistenza «cade al fischio» e «tutto o niente» in paper (`Betfair/safe_strategy/execution.py:514` persistenza
   fissa LAPSE; `:531` tutto o niente su ogni ordine sopra il minimo di Betfair) e in live
   (`Betfair/omega/omega_market.py:735` persistenza fissa LAPSE; `:746` tutto o niente, tolto solo per le bancate
   appoggiate: `service.py:1976`). Ho letto quelle righe e confermano quanto riportato. Conseguenza: l'ultimo
   ingresso non resta sul book; la grazia dei 120 secondi e il caso del punto 1 non hanno oggetto.
3. **Anche la punta d'ingresso dei giri e' «tutto o niente» (da confermare).** Stesse righe: la punta non e' una
   bancata appoggiata, quindi parte «tutto o niente». L'attesa di 60 secondi e il «tengo la parte abbinata» in
   pratica non hanno oggetto. Non ho verificato se l'ordine di 10 euro possa mai finire sotto il minimo di Betfair
   (sotto il minimo la regola cambia).
4. **Veto: la Costituzione non lo nomina.** La Costituzione dice «mai chiudere in perdita prima del fischio» e «in
   perdita -> tengo». Col veto acceso di serie Mike chiude in perdita e non fa l'ultimo ingresso.
5. **Il riprezzo della chiusura finale in pratica non avviene** (Costituzione §16.4-bis punto 27 dice «riprezza»):
   per la regola «mai due bancate a mercato» la bancata nuova viene tolta, la vecchia risulta ritirata e Mike passa
   a «tengo». La posizione entra in gioco invece di essere chiusa. Da confermare col replay.
6. **Ultimo ingresso solo dopo la chiusura finale abbinata** (Costituzione Fase 2 dice «green al mercato + nuovo
   ingresso»): se la chiusura non si abbina, o se a 10 minuti la posizione era gia' piatta, niente ultimo ingresso.
7. **Finestra d'ingresso**: il codice entra da 1 ora prima del fischio; la Costituzione (Fase 1) scrive «da 3 ore
   prima».
8. **Veto ricordato anche senza la tua approvazione**: con le uscite manuali la chiusura del veto e' una proposta, ma
   il veto resta scritto sulla partita: se non approvi, la posizione entra in gioco e l'ultimo ingresso e' vietato.
9. **Punta non abbinata: nessuna pausa e nessun freno sui rifiuti.** Una punta rifiutata dal mercato puo' essere
   ripresentata al giro di controllo dopo.
10. **Tetto di rischio dell'ultimo ingresso**: confronta i 10 euro col tetto intero, non con lo spazio rimasto;
    corretto solo se non ci sono altre puntate vive.
11. **Profitti mostrati non omogenei**: il giro chiuso mostra il lordo, l'uscita al fischio il netto dopo la
    commissione.
12. **Prezzo del primo ingresso**: non viene scritto se la punta e' tenuta in parte per scadenza; viene scritto al
    fischio. Nel frattempo non serve a nulla, poi serve al rientro Under 4,5.

## Punti non chiariti

- La cadenza «circa ogni mezzo secondo» e' il minimo fra due decisioni (`decide_min_interval_ms` 500 ms); non ho
  misurato la cadenza reale.
- Non ho letto come il servizio decide che i dati sono «freschi» oltre ai due valori citati.
