# 06 — RIEPILOGO PER L'UTENTE (08/10/2026)

Due pagine, senza gergo. I numeri vengono dai documenti 00-05 e 07 di questa cartella; ognuno ha la sua fonte la'.

## 1. Cosa abbiamo fatto

Abbiamo letto il software riga per riga (15 schede di componente, scritte da delegati e controllate a campione sul
codice dal coordinatore; una scheda e' stata respinta e corretta perche' conteneva un errore), misurato com'e' oggi
(`07_MISURE_OGGI.md`), studiato i competitor sulle loro fonti pubbliche (`02_COMPETITOR.md`, 63 fonti) e scritto la
struttura nuova (`04`) e l'ordine dei lavori (`05`). Nessuna riga del programma e' stata toccata.

Il software oggi fa **970 cose distinte** (elenco in `01_FUNZIONALITA.md`, ognuna con il punto del codice dove vive).
Il piano assegna OGNUNA di queste 970 voci a una tappa con la sua prova di parita' (controllato con uno strumento: 0 voci
senza tappa). **Nessuna funzionalita' si perde.**

## 2. Com'e' oggi, in parole semplici

- **Ogni cosa e' scritta piu' volte.** Ogni bot ha il suo modo di parlare col database, di ricevere i comandi, di salvare
  lo stato, di contare il P&L. Esempi: 7 strade diverse per mandare un ordine a Betfair, 9 modi diversi di controllare che
  gli ordini tornino, 4 definizioni diverse di «oggi», 6 copie del calcolo del green-up. Per cambiare la strada di un ordine
  oggi si toccano almeno 24 file; per sostituire Omega si toccano 12 zone, tre delle quali sono altri bot.
- **Il database fa da postino fra i programmi.** Mike, Safe e Omega leggono i prezzi e i comandi dal database a giri di
  1-5 secondi; un ordine messo in coda sul database impiega in mediana mezzo secondo e nel caso peggiore 26 secondi
  (misurato su ordini paper). Lo scalper e i bot tennis invece decidono sul tick, senza rete: sono gia' «al millisecondo».
- **Fragilita' h24**: se il guardiano di un servizio cade nessuno lo riavvia; chiudere la finestra spegne tutto; l'orologio
  del PC e' avanti di 0,84 secondi e il servizio dell'ora di Windows e' fermo; un registro del banco ha scritto 1,1 GB.
- **Feed**: in partita arrivano in media 10 messaggi al secondo per mercato, ma ci sono circa 10 buchi all'ora oltre 5 secondi.

## 3. Cosa cambia

- **Ogni componente in UNA cartella**, con un documento che dice cosa fa e un «contratto» scritto (cosa riceve, cosa
  restituisce). Per sostituire un pezzo si tocca solo la sua cartella: e' il criterio con cui si accetta ogni tappa.
- **Il percorso Betfair → decisione → ordine non passa piu' dal database.** Lo stato vivo sta in memoria e su un archivio
  locale (SQLite, scelto perche' ha vinto la prova misurata: 0,6 ms per una scrittura che sopravvive al crash del programma, contro
  21 ms di rete verso il cloud; [revisione critica 08/10] lo spegnimento improvviso del PC NON e' stato provato: per il denaro vale la tenuta
  dichiarata da SQLite, le ultime righe dei registri di attivita' possono perdersi). Un «postino» copia tutto nel database cloud in
  sottofondo, senza doppioni, anche dopo un'assenza di rete.
- **Una sola porta per gli ordini**, una sola riconciliazione, un solo modo di contare soldi e giornate, un solo servizio
  per i punteggi, un solo supervisore dei processi (da 18 processi a 8).
- **I pannelli della app nascono dal contratto dei bot** (come gia' oggi il catalogo del replay): un parametro si scrive in un
  posto solo e non puo' piu' divergere fra bot e schermo (oggi lo scalper ha gia' un valore di serie diverso fra i due).
- **Il ladder alla app** passa da un aggiornamento ogni 200 ms a un aggiornamento a ogni cambio (Bet Angel dichiara 20 ms).

## 4. Cosa resta identico

- **Le strategie**: ogni regola, soglia, stake e cancello resta identico; si sposta, non si riscrive. Una «impronta»
  automatica della strategia deve dare 0 differenze a ogni tappa.
- **Il database cloud resta l'archivio generale**: tutte le tabelle continuano a riempirsi; gli algoritmi che lo usano
  (modello di Mike, tabelle empiriche di Omega, previsioni, statistiche, scanner, P&L del conto) restano, con le stesse
  regole di aggiornamento.
- Paper e live separati, calcio e tennis separati, bot accesi solo da te, uscite manuali di serie.
- **La app attuale resta in produzione per tutto il tempo**: ogni pezzo nuovo gira prima «in ombra» accanto al vecchio, con
  confronto automatico numero per numero sulle registrazioni vere; sostituisce il vecchio solo se e' identico, e si torna
  indietro con un interruttore.

## 5. Una verita' sui numeri: l'80% di righe in meno

**Non e' dimostrabile per il software intero**, e il piano non lo promette. Con le stime delle schede: **-10,4%** delle righe [coerenza 08/10: era «-10%», allineato a 04 §10]
senza nessuna tua decisione, **-17,5%** accogliendo tutte le proposte. Il motivo e' misurato: la strategia, che non si tocca,
e' una parte grande; un terzo dei programmi principali e' commento che spiega incidenti passati; le copie identiche parola per
parola sono poche (lo stesso lavoro e' scritto in modi diversi). Dove il taglio e' grande e reale: il guscio attorno ai bot
(-59%), lo strato del database (-63%), il guscio di Mike (-73%), la contabilita' (-67%), i punteggi (-52%). Il vero guadagno
e' un altro: **una copia invece di 3-6 per ogni cosa, zero rete nel percorso dei soldi, un solo punto da toccare per
cambiare un pezzo.**

## 6. Quanto ci vuole

29 tappe piccole (`05`), ognuna con prova di parita', interruttore e ritorno indietro. **Circa 16-20 settimane** ([revisione critica 08/10]: prima 13-17; il calcolo aveva saltato due tappe obbligate) lavorando su
due linee (il cloud costruisce e certifica, il PC misura, prova in ombra e firma); circa 10-12 settimane ([revisione critica 08/10]: prima 8-10) per la sola parte che
avevi gia' deciso il 02/10, piu' del doppio di quanto stimato allora, perche' i replay di oggi sono lenti (Mike 12 minuti, scalper
quasi 2 ore per tutti gli scenari) e perche' ora ogni tappa ha il congelamento dei riferimenti e il periodo in ombra.
**Prima tappa**: il pannello «Salute» (misure vere di CPU, memoria, feed, database, tempi degli ordini) e il congelamento
delle registrazioni e dei referti di riferimento.

## 7. Le decisioni che servono da te

Sono 86 (79 + 7 aggiunte dalla revisione critica dell'08/10), tutte in `05_PIANO_DI_MIGRAZIONE.md` §8, con l'effetto e cosa succede se non decidi (in quel caso il piano non
cambia nulla di strategia). **Bloccano l'inizio (tappa 0):**

1. **U-62** Accendere il servizio dell'ora di Windows, impedire la sospensione del PC, avvio della app all'accensione.
2. **U-32** Correggere il finto di Omega nel banco prima di congelare i riferimenti (i referti di Omega cambieranno).
3. **U-27** Autorizzare il riferimento di Mike (replay di ~12 min) e scegliere altre partite complete: oggi Mike e'
   certificato su una sola partita.
4. **U-44** Copiare 3-5 partite di tennis nel repo, cosi' anche il tennis si certifica nel cloud.
5. **U-37** Committare 4 documenti oggi solo sul tuo disco (`SPEC_STRATEGIA_S.md`, `TENNIS_BOT_DOSSIER.md`,
   `ESECUZIONE_LIVE.md`, `SAFE_STRATEGY_DOSSIER.md`).
6. **U-59** Approvare le sole 3 tolleranze del confronto in ombra (orari, impronte del codice, identificativi d'orologio).
7. **U-60** Misurare (o confermare) i 120 ms che il banco assume per ogni lettura a Betfair.

**Le piu' importanti dopo** (cambiano comportamento o soldi, quindi solo tue):
- **U-01** Lo scanner che alimenta Mike, Safe e Omega legge i prezzi con 1 secondo di raggruppamento; i competitor 0-20 ms.
  Abbassarlo cambia cio' che i tre bot vedono: prima un replay, poi decidi tu.
- **U-48** Lo stop giornaliero oggi conta il P&L **lordo**, il conto e' netto: tenere lordo o passare a netto?
- **U-47** Una sola definizione di «giornata» per tutti (oggi 4).
- **U-19** Cosa fa un bot se non riesce a leggere i tuoi comandi (oggi Mike si ferma, Omega e Safe continuano a gestire).
- **U-18** Quando portare Mike live sulla porta unica (oggi e' l'unico bot live che manda ordini per conto suo).
- **U-17** Usare l'«Heartbeat» di Betfair, che cancella gli ordini se il programma muore (ma vale per tutto il conto).
- **U-39** Lo scalper ha `one_green_per_phase` diverso fra bot (no) e schermo (si'): quale vale?
- **U-24** Stop e trailing a ogni tick invece che ogni 0,15 s.
- **U-71/U-73/U-74** Archiviare (mai cancellare) il codice morto: 3.440 righe con prova piena, fino a ~24.000 con le tue
  conferme (fogli Google, 41 script manuali, laboratori).

**[revisione critica 08/10] Aggiunte importanti** (dettaglio in `08_REVISIONE_CRITICA.md`):
- **U-80** Come numerare i trade quando il cloud non e' piu' nel percorso: oggi il numero del cloud e' anche il riferimento
  dell'ordine di Mike su Betfair. Proposta: numeri riservati in anticipo, cosi' tutto resta identico.
- **U-83** Chi riaccende il supervisore se la finestra e' chiusa, e se un suo crash debba spegnere anche i runner con posizioni
  aperte (proposta: no, i runner restano vivi e vengono ripresi).
- **U-84** Aggiornamenti di Windows (niente riavvii automatici con posizioni aperte) e versioni dei programmi bloccate fino alla fine.
- **U-85** La prova della contabilita' chiede 5 giornate live di fila: se non operi live, accettare giornate con regolamenti reali
  anche manuali.

## 8. Cosa NON abbiamo potuto verificare

CPU e memoria della app (era spenta), il tempo vero di un ordine live (nella storia c'e' 1 sola richiesta live misurata), il
ritardo reale dei punteggi, la durata dei replay dopo il cantiere 11. Il pannello «Salute» della tappa 0 serve proprio a
misurarli prima di cambiare qualunque cosa.
