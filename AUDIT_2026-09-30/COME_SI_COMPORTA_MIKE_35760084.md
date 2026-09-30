# Come si comporta Mike: Liepajas Metalurgs - Ogre United (30/06/2026, finita 4-0)

Registrazione 35760084. Il codice è quello definitivo di oggi (master `55b0ce0`).
Tutte le cifre vengono da tre replay rifatti oggi. Ogni replay è passato dal punto d'ingresso
vero della certificazione (`replay_registrazioni.certifica_scenario`, canale, ambiente neutro,
nessun database vero). Una sonda di sola lettura ha registrato ogni decisione del motore, ogni
riga del diario (la tabella `mike_activity`) e ogni riga degli ordini (la tabella `mike_trades`).
Gli orari sono italiani (UTC+2). Gli importi sono in euro, con due decimali e il segno.

I totali coincidono con il referto ufficiale di oggi `AUDIT_2026-09-30/replay/mike_tutti_FINALE.txt`:

| Percorso | Scenario | Decisioni del motore (sonda / referto) | Decisioni che cambiano qualcosa | Risultato (sonda) | Risultato (referto ufficiale) |
|---|---|---|---|---|---|
| A. Nessuno firma | `base` | 5.861 / 5.861 | 45 | **-14,17** | -14,17 ✔ |
| B. Firmi la prima proposta dopo il 4° gol | `firma-dopo-gol-decisivo` | 5.853 / 5.853 | 35 | **-2,14** | -2,14 ✔ |
| C. Copertura vecchia (punta Over 4,5) | `copertura-legacy` | 5.861 / 5.861 | 45 | **-14,00** | -14,00 ✔ |

Nei tre percorsi coincidono anche i conteggi delle righe di diario (per esempio: A e C hanno 18 proposte
e 16 decadute, B ne ha 12 e 9), gli ordini piazzati (5, 7 e 5) e le commissioni per mercato.
Nella tabella, «decisioni che cambiano qualcosa» sono i giri in cui Mike cambia stato, manda o annulla
un ordine, fa o ritira una proposta, calcola una copertura o regola la partita. In tutti gli altri giri
Mike ripete «tengo» oppure «prezzi incompleti».

---

## 1. In dieci righe

1. **Prima della partita** Mike **punta** (back) 10,00 € sull'**Under 3,5** (al massimo 3 gol a fine partita), se la quota è fra 1,30 e 3,00, c'è abbastanza denaro in lista e lo scarto fra punta e banca è stretto.
2. Appena la puntata è abbinata, Mike lascia in lista una **banca** (lay) **2 tick sotto** la quota d'ingresso. Il tick è il più piccolo passo di quota. Se quella banca si abbina, il guadagno è bloccato (green-up) su ogni risultato.
3. **10 minuti prima del fischio** Mike smette di entrare e tiene la posizione. Al passaggio in gioco Betfair cancella gli ordini in lista (persistenza LAPSE, cioè l'ordine scade).
4. **Al fischio** Mike rimette la stessa banca a 2 tick sotto e le dà **3 minuti** di tempo.
5. Se in 3 minuti non si abbina, Mike la **annulla** e si **copre sulla linea 4,5**.
6. Di serie la copertura è una **BANCA sull'Under 4,5**. L'importo è `perdita Under 3,5 × 1,2 / 0,95`. Con 5 o più gol quella banca paga l'1,2 della puntata persa sull'Under 3,5 (commissione già tolta).
7. Da quel momento il caso peggiore è **finire con 4 gol esatti**: l'Under 3,5 perde e perde anche la copertura.
8. Mike ricalcola sempre il valore di **chiudere adesso** e quello di **tenere fino alla fine**. Quando chiudere conviene, con le **uscite manuali** (l'impostazione di serie) **non chiude da solo**: ti fa una **proposta** («USCITA PROPOSTA: DECIDI TU»). Se il conto cambia, la proposta decade.
9. A fine partita Betfair regola i due mercati. La commissione è il 5 % del guadagno netto di **ogni mercato**, arrotondata al centesimo.
10. Risultati di questa partita: **A -14,17 €**, **B -2,14 €**, **C -14,00 €**.

---

## 2. Percorso A: nessuno firma (scenario `base`, copertura di serie = banca Under 4,5)

### 2.1 Cronaca

Le quote sono scritte come «punta / banca», cioè il miglior prezzo per puntare e quello per bancare in quel momento.

| Ora | Minuto | Punteggio | Cosa succede | Cosa fa Mike e perché | Numeri | Cosa vedi nell'app |
|---|---|---|---|---|---|---|
| 17:06:01 | pre | – | Primo giro sulla registrazione. Under 3,5 a 1,70 / 1,75. | **Non entra.** Al miglior prezzo ci sono solo 8,02 € e ne servono 10,00. | «liquidita 8.02 < 10.00» | Stato «IN ATTESA» |
| 17:07:11 | pre | – | Lo scarto fra punta e banca si allarga (1,66 / 1,75). | **Non entra**: lo scarto è di 9 tick, oltre il limite di 6. | «spread 9 tick» | «IN ATTESA» |
| 17:08:09 | pre | – | Under 3,5 a 1,71 / 1,75, denaro sufficiente. | **Punta 10,00 € sull'Under 3,5 a 1,71.** L'ordine è abbinato subito, per intero. | Puntata 10,00 @ 1,71. Rischio 10,00 €. | «ORDINE» (ingresso Under 3,5 punta 10,00 @ 1,71), «FASE: IN ATTESA → INGRESSO IN CORSO» |
| 17:08:11 | pre | – | – | **Lascia in lista una banca Under 3,5 a 1,69** (2 tick sotto 1,71) per bloccare il guadagno. | Banca 10,12 @ 1,69. 10 × 1,71 / 1,69 = 10,12. Se si abbina: +0,12 € lordi su ogni risultato. | «ORDINE APPOGGIATO», «FASE: INGRESSO IN CORSO → UNDER 3.5 APERTO» |
| 17:08 → 17:50 | pre | – | L'Under 3,5 sale a 1,75-1,82: il mercato crede meno ai pochi gol. | La banca a 1,69 non trova controparte e **resta in lista**. | – | «UNDER 3.5 APERTO» |
| 17:50:01 | pre | – | Mancano 10 minuti al fischio. | **Nessun nuovo ingresso.** La banca resta in lista fino al fischio. | Regola «ultimo ingresso» = 10 minuti | «FASE: … → TIENE FINO AL FISCHIO» |
| 18:00:25 | – | – | Il mercato passa in gioco. Betfair cancella la banca in lista (LAPSE). | Mike legge l'esito: «scaduto». | Riga 2 in `mike_trades`: stato `error`, esito «cancellato da Betfair» | «NON ABBINATO» (motivo «runner_scaduto») |
| 18:00:30 | 0' | 0-0 | Partita in gioco. | **Passa alla fase «uscita al fischio».** Da qui partono i 3 minuti. | Finestra = 180 secondi | «FASE: → USCITA AL FISCHIO» |
| 18:00:31 | 0' | 0-0 | – | **Rimette la banca Under 3,5 a 1,69** (2 tick sotto l'ingresso). | Banca 10,12 @ 1,69 in lista | «ORDINE APPOGGIATO» |
| 18:00:40 → 18:01:52 | – | – | Il feed non porta il punteggio per 82 secondi. | Mike non decide niente sui gol finché il punteggio manca. | – | «LINEA ASSENTE NEL FEED» (rosso), poi «SALTO · il punteggio è tornato» |
| 18:01:58 | 0' | 0-0 | Il mercato 3,5 si sospende. Betfair cancella la banca. | Mike vede «scaduto» e aspetta la riapertura. | Riga 3: esito «cancellato da Betfair» | «NON ABBINATO» |
| 18:02:00 | 0' | 0-0 | Il mercato riapre. | **Rimette la banca a 1,69** (i 3 minuti continuano a scorrere dalle 18:00:30). | Banca 10,12 @ 1,69 | «ORDINE APPOGGIATO» |
| 18:03:31 | 2' | 0-0 | Sono passati 3 minuti e la banca non si è abbinata. Under 3,5 a 1,73 / 1,78. | **Annulla la banca** e dichiara la partita da coprire. Betfair conferma l'annullo. | Annullati 10,12 €, abbinati 0,00 € | «ANNULLO CHIESTO A BETFAIR», «ANNULLO: ESITO DA BETFAIR», «FASE: USCITA AL FISCHIO → IN GIOCO · SCOPERTO» («uscita non abbinata in 3': copertura Over 4.5») |
| 18:03:32 | 2' | 0-0 | Under 4,5 a 1,30 / 1,33. | **Copertura: banca Under 4,5.** L'importo è 12,63 €. Il prezzo limite è 1,35 (2 tick di margine sopra il miglior prezzo di banca, 1,33). L'ordine si abbina tutto a 1,33. | **X = 10,00 × 1,2 / (1 − 0,05) = 12,63.** Rischio = 12,63 × (1,33 − 1) = **4,17 €** (sarebbe stato 4,42 € al limite 1,35). Equivale a puntare l'Over 4,5 a circa 4,0. | «COPERTURA LINEA 4.5», «ORDINE» (banca 12,63 @ 1,33), «FASE: → COPERTURA IN CORSO» |
| 18:03:38 | 2' | 0-0 | – | Copertura abbinata. | Posizione: +10,00 Under 3,5 @ 1,71 e −12,63 Under 4,5 @ 1,33 | «FASE: → IN GIOCO · COPERTO» |
| 18:09:04 | 7' | 1 gol | Primo gol. | **Tiene.** Nessuna regola di uscita scatta. | Under 3,5 a 2,32 / 2,90 | – |
| 18:29:37 | 28' | 2 gol | Secondo gol. | **Tiene.** | Under 3,5 a 3,55 / 4,70 | – |
| 18:47:15 | – | 2 gol | Il controllo del flusso prezzi dichiara «fermo» il mercato 4,5 (da 2.805 secondi). | Scrive l'allarme e non cambia posizione (vedi §7, punto 3). | Esposizione dichiarata 14,17 € | «FLUSSO PREZZI INTERROTTO» e «FLUSSO FERMO E REST MUTO: POSIZIONE SCOPERTA» (rossi) |
| 18:47:51 | 45'+1 | 3 gol | Terzo gol, nel recupero del primo tempo. | **Tiene.** Il caso peggiore (4 gol esatti) adesso è a un gol di distanza. | Under 3,5 a 7,0 / 12,5, Over 4,5 a 1,58 / 1,82 | – |
| 18:48:25 | 45'+2 | 3 gol | – | **Prima proposta di uscita.** Chiudere tutto adesso blocca **-2,45 €**. Tenere vale in media -2,23 €. A questo si toglie un premio di prudenza di 0,38 €, e la soglia diventa -2,61 €. Siccome -2,45 è migliore di -2,61, **conviene chiudere**. Con le uscite manuali **ti propone** la chiusura e non la esegue. | Ordini proposti: banca Under 3,5 1,90 @ 9,0 + banca Over 4,5 10,12 @ 1,66. Probabilità di finire con 4 gol esatti (P4) = 27 %. Premio = 14,17 × 10 % × 0,27 = 0,38. | «USCITA IN PERDITA DECISA», «USCITA PROPOSTA: DECIDI TU» (arancione, urgente), con la cifra -2,45 |
| 18:49 → 19:03 | intervallo | 3 gol | – | La proposta **resta viva** durante l'intervallo. | – | La proposta resta sulla scheda |
| 19:03:38 | 45' (2° t.) | 3 gol | Riprende il gioco. | **Aggiorna la proposta** con i prezzi nuovi. | Chiudere -2,18, tenere -2,05, premio 0,36, P4 25 % | «USCITA PROPOSTA: DECIDI TU» (-2,18) |
| 19:07:56 → 19:23:50 | 46'-61' | 3 gol | Le quote oscillano. | La proposta **nasce e decade** più volte. Decade quando tenere torna a valere di più oppure quando mancano i prezzi. In questo tratto le cifre proposte vanno da **-2,15 a -3,50**. | 10 proposte e 9 decadute fra le 19:07 e le 19:23 (tabella in §2.2) | Si alternano «USCITA PROPOSTA: DECIDI TU» e «PROPOSTA DI USCITA DECADUTA» |
| 19:23:50 | 61' | 3 gol | Il mercato si sospende (è il 4° gol in arrivo). | La proposta decade per «prezzi incompleti». | – | «PROPOSTA DI USCITA DECADUTA» |
| 19:25:17 | 63' | **4 gol** | **Quarto gol.** Betfair sospende e poi **chiude** il mercato 3,5: l'Under 3,5 è **perso**. | Scrive che la linea 3,5 è decisa. Da qui ragiona solo sulla linea 4,5. | Esito: Under 3,5 «persa» | «LINEA DECISA DAI GOL» |
| 19:25:33 | 64' | 4 gol | Over 4,5 a 1,27 / 1,35. | **Nuova proposta: chiudere la sola copertura** con una banca Over 4,5. Chiudere blocca **-2,14 €**. Tenere vale -1,85 €, meno un premio di 0,34 €: soglia -2,19 €. Siccome -2,14 è migliore di -2,19, **conviene chiudere**. **Ti propone**, non esegue. | Ordine proposto: banca Over 4,5 12,44 @ 1,35. P4 = 24 %: il mercato dà al 76 % un quinto gol. | «USCITA PROPOSTA: DECIDI TU» (-2,14). **È la proposta che nel percorso B firmi.** |
| 19:25:38 → 19:41:45 | 64'-79' | 4 gol | Il quinto gol non arriva. L'Over 4,5 sale da 1,35 a 2,00. | Proposte e decadimenti si alternano. **Ogni nuova proposta è peggiore della precedente**: -2,14, -2,14, -2,23, -2,96, -4,11, -5,91, -5,98. | P4 sale dal 24 % al 46 % | «USCITA PROPOSTA» / «PROPOSTA DI USCITA DECADUTA» |
| 19:41:45 | 79' | 4 gol | – | Ultima proposta decaduta. Da qui Mike **tiene** fino alla fine. Non propone più perché tenere torna a valere di più di chiudere. | – | «PROPOSTA DI USCITA DECADUTA» |
| 19:53:04 / 19:54:06 | 90'+ | 4 gol | Fine partita: il flusso del 4,5 si ferma e la linea sparisce dal feed. | Scrive gli allarmi. Non ha ordini da fare. | – | «FLUSSO PREZZI INTERROTTO», «FLUSSO FERMO E REST MUTO…», «LINEA ASSENTE NEL FEED» |
| 19:54:13 | – | 4-0 finale | Betfair chiude il mercato 4,5: l'Under 4,5 **vince**, quindi la nostra banca **perde**. | – | – | – |
| 20:04:17 | – | 4-0 | – | **Regola la partita** (vedi sotto). Nel replay il regolamento cade 10 minuti dopo l'ultimo prezzo, perché il banco fa girare il servizio ancora 601 volte a mercati chiusi. | **-14,17 €** | «FASE: IN GIOCO · COPERTO → IN REGOLAMENTO → REGOLATA», «REGOLATA» con P&L -14,17 |

### 2.2 Le 18 proposte di uscita del percorso A

| Ora | Minuto | Gol | Chiudendo ora | Tenere (media) | Premio | Soglia | Ordini proposti |
|---|---|---|---|---|---|---|---|
| 18:48:25 | 47 | 3 | -2,45 | -2,23 | 0,38 | -2,61 | banca U3,5 1,90 @ 9,0 + banca O4,5 10,12 @ 1,66 |
| 19:03:38 | 45 (2° t.) | 3 | -2,18 | -2,05 | 0,36 | -2,41 | banca U3,5 1,63 @ 10,5 + banca O4,5 10,70 @ 1,57 |
| 19:07:56 | 46 | 3 | -2,15 | -1,99 | 0,36 | -2,35 | U3,5 1,71 @ 10,0 + O4,5 10,63 @ 1,58 |
| 19:08:47 | 46 | 3 | -2,28 | -2,05 | 0,36 | -2,41 | U3,5 1,71 @ 10,0 + O4,5 10,50 @ 1,60 |
| 19:09:03 | 47 | 3 | -2,43 | -2,12 | 0,37 | -2,48 | U3,5 1,63 @ 10,5 + O4,5 10,43 @ 1,61 |
| 19:09:27 | 48 | 3 | -2,31 | -2,04 | 0,36 | -2,40 | U3,5 1,74 @ 9,8 + O4,5 10,43 @ 1,61 |
| 19:19:34 | 57 | 3 | -2,93 | -3,06 | 0,45 | -3,52 | U3,5 2,85 @ 6,0 + O4,5 8,61 @ 1,95 |
| 19:20:23 | 59 | 3 | -3,29 | -3,10 | 0,46 | -3,55 | U3,5 2,85 @ 6,0 + O4,5 8,23 @ 2,04 |
| 19:20:33 | 59 | 3 | -3,25 | -3,12 | 0,46 | -3,58 | U3,5 2,90 @ 5,9 + O4,5 8,23 @ 2,04 |
| 19:22:48 | 61 | 3 | -3,50 | -3,39 | 0,48 | -3,87 | U3,5 3,29 @ 5,2 + O4,5 7,57 @ 2,22 |
| 19:23:48 | 61 | 3 | -3,43 | -3,91 | 0,53 | -4,44 | U3,5 3,35 @ 5,1 + O4,5 7,57 @ 2,22 |
| 19:25:33 | 64 | 4 | **-2,14** | -1,85 | 0,34 | -2,19 | banca O4,5 12,44 @ 1,35 |
| 19:25:41 | 64 | 4 | -2,14 | -1,85 | 0,34 | -2,19 | banca O4,5 12,44 @ 1,35 |
| 19:27:20 | 66 | 4 | -2,23 | -2,21 | 0,37 | -2,57 | banca O4,5 12,35 @ 1,36 |
| 19:30:38 | 69 | 4 | -2,96 | -2,79 | 0,42 | -3,21 | banca O4,5 11,58 @ 1,45 |
| 19:35:21 | 73 | 4 | -4,11 | -3,68 | 0,50 | -4,18 | banca O4,5 10,37 @ 1,62 |
| 19:41:04 | 79 | 4 | -5,91 | -5,40 | 0,65 | -6,05 | banca O4,5 8,48 @ 1,98 |
| 19:41:36 | 79 | 4 | -5,98 | -5,40 | 0,65 | -6,05 | banca O4,5 8,40 @ 2,00 |

Come leggere la tabella: **«Tenere (media)»** è la media dei risultati finali possibili, pesati con la
probabilità di ciascun numero di gol secondo il modello (dopo il 4° gol conta solo il modello, perché il
mercato 3,5 è chiuso). **«Premio»** = 10 % × probabilità di finire con 4 gol esatti × 14,17 (la perdita
massima). **«Soglia»** = tenere − premio. Mike propone di chiudere quando «chiudendo ora» è uguale o
migliore della soglia.

Le 16 decadute sono tutte «la strategia non vuole più uscire». Il motivo è «tengo» in 12 casi e «prezzi
incompleti» in 4 casi (19:20:20, 19:23:46, 19:23:50, e la sospensione del 4° gol).

### 2.3 Il regolamento del percorso A, riga per riga

| Riga `mike_trades` | Ordine | Chiesto | Abbinato | Esito Betfair | Lordo | Commissione | Netto |
|---|---|---|---|---|---|---|---|
| 1 | Punta Under 3,5 @ 1,71 (ingresso) | 10,00 | 10,00 @ 1,71 | **perso** (4 gol > 3,5) | -10,00 | 0,00 | **-10,00** |
| 2 | Banca Under 3,5 @ 1,69 (green-up pre-partita) | 10,12 | 0,00 | cancellato da Betfair (passaggio in gioco) | 0,00 | – | 0,00 |
| 3 | Banca Under 3,5 @ 1,69 (uscita al fischio) | 10,12 | 0,00 | cancellato da Betfair (sospensione) | 0,00 | – | 0,00 |
| 4 | Banca Under 3,5 @ 1,69 (uscita al fischio, seconda) | 10,12 | 0,00 | annullato da Mike dopo 3 minuti | 0,00 | – | 0,00 |
| 5 | Banca Under 4,5 @ 1,33 (copertura) | 12,63 | 12,63 @ 1,33 | **perso** (4 gol < 4,5: l'Under vince, la banca paga) | -4,17 | 0,00 | **-4,17** |
| | **Mercato 3,5** | | | | -10,00 | 0,00 | -10,00 |
| | **Mercato 4,5** | | | | -4,17 | 0,00 | -4,17 |
| | **Totale** | | | | **-14,17** | **0,00** | **-14,17** |

Nell'app le righe 2, 3 e 4 hanno stato `error`, con l'esito scritto a parte. Le righe 1 e 5 sono `lost`.
Il referto ufficiale dice lo stesso («righe per stato: lost 2, error 3»). Il P&L scritto da Mike (-14,17)
è uguale al P&L calcolato dal banco con la regola di Betfair (-14,17).

### 2.4 Perché ha perso 14,17

- La partita è finita **esattamente con 4 gol**. È l'unico risultato in cui perdono **entrambe** le gambe: l'Under 3,5 perde 10,00 € e la banca Under 4,5 perde 4,17 €.
- Il green-up pre-partita non si è abbinato: l'Under 3,5 si è **allontanato** (da 1,71 a 1,75-1,82) invece di scendere.
- L'uscita al fischio non si è abbinata in 3 minuti. Così la copertura è partita al 2', con lo 0-0.
- Dopo il 3° gol e dopo il 4° gol Mike ha **proposto** di chiudere a cifre fra -2,14 e -5,98. Con le uscite manuali nessuno ha firmato, quindi Mike ha tenuto.
- Il quinto gol non è arrivato. Il mercato lo dava al 76 % al 64'. È stato il caso sfavorevole.

---

## 3. Percorso B: l'utente firma la prima proposta dopo il quarto gol (scenario `firma-dopo-gol-decisivo`)

Fino alle 19:25:33 tutto è **identico ad A**: stessi ordini, stessi prezzi, stesse 11 proposte prima del 4° gol.

| Ora | Minuto | Punteggio | Cosa succede | Cosa fa Mike e perché | Numeri | Cosa vedi nell'app |
|---|---|---|---|---|---|---|
| 19:25:17 | 63' | 4 gol | Quarto gol, il mercato 3,5 è deciso. | Come in A. | – | «LINEA DECISA DAI GOL» |
| 19:25:33 | 64' | 4 gol | Arriva la proposta: chiudere a -2,14. **Tu la firmi** (nel replay la firma è la richiesta vera `approva_uscita`, la stessa che manda il pulsante dell'app). | Registra la tua approvazione. | Proposta «chiusura\|c0», banca Over 4,5 12,44 @ 1,35, bloccabile -2,14 | «USCITA PROPOSTA: DECIDI TU» e subito «USCITA APPROVATA (utente)» |
| 19:25:34 | 64' | 4 gol | Over 4,5 a 1,27 / 1,35. | **Esegue la tua firma** con i prezzi di quel momento. Prima prova: al miglior prezzo di banca (1,35) ci sono solo 3,00 €. Mike riduce l'ordine a 3,00 € «tutto o niente» (FOK: si abbina per intero o si annulla), per non restare con un'uscita a metà. L'ordine **non si abbina** e si annulla. | Riga 6: chiesto 12,44, ridotto a 3,00, abbinato 0,00, esito «non abbinato (tutto o niente)» | «USCITA ESEGUITA SU APPROVAZIONE», «FASE: IN GIOCO · COPERTO → CHIUSURA IN CORSO», «NON ABBINATO» |
| 19:25:41 | 64' | 4 gol | Over 4,5 a 1,22 / 1,35. | **Riprova la chiusura del resto**: banca Over 4,5 12,44 @ 1,35. Questa volta si abbina per intero. | Riga 7: 12,44 abbinati, prezzo medio 1,35. Rischio 12,44 × 0,35 = 4,35 € | «ORDINE» (banca Over 4,5 12,44 @ 1,35) |
| 19:25:47 | 64' | 4 gol | – | La posizione è piatta: il risultato è bloccato. | Stato «PIATTA», motivo «chiuso (loss_2t)» (uscita in perdita, secondo tempo) | «FASE: CHIUSURA IN CORSO → PIATTA» |
| 19:25:49 → 20:04 | – | – | Il resto della partita. | Nessuna decisione: 1.132 giri «flat» (niente da fare). Gli allarmi di fine flusso delle 19:53 e 19:54 compaiono lo stesso. | – | «PIATTA» |
| 20:04:17 | – | 4-0 | – | **Regola la partita.** | **-2,14 €** | «REGOLATA» -2,14 |

### 3.1 Il conto della chiusura

La copertura (banca Under 4,5 12,63 @ 1,33) equivale a una puntata sull'Over 4,5:

- con 5 o più gol incassa **+12,63**;
- con 4 o meno gol perde **-4,17**.

Per chiuderla Mike banca l'Over 4,5 a 1,35 con un importo S che rende uguali i due esiti:

- 5+ gol: 12,63 − 0,35 × S
- 0-4 gol: −4,17 + S
- Uguali quando 16,80 = 1,35 × S, cioè **S = 12,44**.

Mercato 4,5 dopo la chiusura: +8,27 lordi con 4 gol (+8,28 con 5 o più, per arrotondamento).

### 3.2 Il regolamento del percorso B, riga per riga

| Riga | Ordine | Abbinato | Esito | Lordo | Commissione | Netto |
|---|---|---|---|---|---|---|
| 1 | Punta Under 3,5 @ 1,71 | 10,00 | perso | -10,00 | 0,00 | -10,00 |
| 2-4 | Bancate green-up / uscita al fischio | 0,00 | cancellate / annullata | 0,00 | – | 0,00 |
| 5 | Banca Under 4,5 @ 1,33 | 12,63 | perso | -4,17 | – | -4,17 |
| 6 | Banca Over 4,5 @ 1,35 (primo tentativo, 3,00 tutto o niente) | 0,00 | non abbinato | 0,00 | – | 0,00 |
| 7 | Banca Over 4,5 @ 1,35 (chiusura) | 12,44 | **vinto** (Over 4,5 perde) | +12,44 | – | – |
| | **Mercato 3,5** | | | -10,00 | 0,00 | -10,00 |
| | **Mercato 4,5** | | | +8,27 | **0,41** (5 % di 8,27) | +7,86 |
| | **Totale** | | | **-1,73** | **0,41** | **-2,14** |

Mike attribuisce la commissione alla gamba vincente: nel diario la riga 7 porta 12,03 netti, cioè
12,44 − 0,41. Il referto ufficiale dice lo stesso: «lordo -1,73, commissione 0,41, netto -2,14», con
0,41 sul mercato 4,5 e 0,00 sul 3,5.

### 3.3 Cosa sarebbe cambiato firmando

- **Firmando: -2,14 €. Senza firma: -14,17 €. Differenza: +12,03 €.** In questa partita la firma ha pagato perché il quinto gol non è arrivato.
- Il prezzo della firma: da quel momento il risultato è -2,14 **qualunque** cosa succeda. Con un quinto gol, senza firma, avresti chiuso a **+2,00** (percorso A, §5). Firmando rinunci a quei +2,00 per non rischiare -14,17.
- Mike ha proposto la chiusura perché, con un 76 % di probabilità di quinto gol, tenere valeva in media -1,85. Il premio di prudenza sui 4 gol esatti (0,34) ha fatto pendere la bilancia verso la chiusura: -2,14 contro la soglia di -2,19. Il margine era di soli **5 centesimi**.

---

## 4. Percorso C: la copertura vecchia, punta Over 4,5 (scenario `copertura-legacy`)

È tutto uguale ad A fino alle 18:03:31. Cambia **solo come si scrive la copertura**. Il momento e l'obiettivo di protezione restano gli stessi.

| Ora | Cosa fa Mike | Numeri |
|---|---|---|
| 18:03:32 | **Punta l'Over 4,5.** Il miglior prezzo è 4,0 e il limite è 3,9 (2 tick di margine). | Importo chiesto **X = 1,2 × 10,00 / ((4,0 − 1) × 0,95) = 4,21 €** |
| 18:03:32 | L'ordine è abbinato per **4,00 €** a 4,0, non per 4,21. | Riga 5: chiesti 4,21, abbinati 4,00, prezzo medio 4,0 |
| 18:03:38 | Copertura abbinata, stato «IN GIOCO · COPERTO». | – |
| 18:48 → 19:41 | Stesse 18 proposte e 16 decadute di A, ma con cifre un po' peggiori. Per esempio, alla prima proposta dopo il 4° gol chiudere vale -2,54 (in A -2,14), con banca Over 4,5 11,85 @ 1,35. | – |
| 20:04:17 | Regolamento: Under 3,5 -10,00, punta Over 4,5 -4,00. | **-14,00 €** (lordo -14,00, commissione 0,00) |

**Perché 4,00 e non 4,21.** Su Betfair Italia una **puntata** (back) deve essere di almeno 2,00 € e
salire a **passi di 0,50 €**. 4,21 non è un importo valido, quindi si abbinano solo 4,00. Con 5 o più
gol la copertura avrebbe reso 4,00 × 3 × 0,95 = 11,40 invece di 12,00: una protezione più bassa del
dichiarato. Una **bancata** invece va da 0,50 € in su, al centesimo. Per questo la banca Under 4,5 di
12,63 € entra esatta.

**Perché oggi la copertura di serie è la banca (decisione P5 del 29/09).**

1. **L'importo è sempre piazzabile**: minimo 0,50 €, nessun passo. La punta Over 4,5 invece cade spesso sotto i 2,00 € o fuori passo. Il 17/09 (reperto 25) una copertura sotto il minimo è stata rifiutata 104 volte in un'ora. Il 12/09 (Koper - Olimpija) una copertura da 1,91 € è stata rifiutata 172 volte e la partita è finita -16,16 € senza copertura.
2. **La protezione è quella dichiarata**: con 5 o più gol la banca incassa 12,63 × 0,95 = 12,00, cioè esattamente 1,2 × la puntata persa.
3. **La strategia non cambia**: stesso momento, stesso margine, stesse tranche. L'interruttore `cover_form` nell'app riporta alla punta Over 4,5 dal giro successivo.

**Il costo.** Su questa partita la banca è costata **0,17 €** in più (-14,17 contro -14,00). La banca
Under 4,5 rischia 4,17 € contro i 4,00 € della punta, perché la punta si è fermata a 4,00 invece di 4,21.

---

## 5. Se la partita fosse finita diversamente

Le posizioni sono quelle abbinate a fine partita in A e in C. Nessuno firma. Le cifre sono calcolate
con la regola di Betfair del banco: guadagno per scommessa al centesimo, commissione del 5 % sul netto
vincente di ciascun mercato, arrotondata al centesimo. Accanto c'è la cifra del motore di Mike
(`net_pnl_by_total`), quando è diversa.

| Gol a fine partita | A: banca Under 4,5 (12,63 @ 1,33) | C: punta Over 4,5 (4,00 @ 4,0) |
|---|---|---|
| **0-3 gol** | Under 3,5 vince +7,10, commissione 0,35 → +6,75. Banca U4,5 perde -4,17. **Totale +2,58** | Under 3,5 +7,10 − 0,35 = +6,75. Punta O4,5 perde -4,00. **Totale +2,75** (il motore di Mike dice +2,74: 1 centesimo di arrotondamento) |
| **4 gol** (il caso vero) | -10,00 − 4,17 = **-14,17** | -10,00 − 4,00 = **-14,00** |
| **5 o più gol** | Under 3,5 -10,00. Banca U4,5 vince +12,63, commissione 0,63 → +12,00. **Totale +2,00** | Under 3,5 -10,00. Punta O4,5 vince 4,00 × 3 = +12,00, commissione 0,60 → +11,40. **Totale +1,40** |

Come leggere la tabella:

- La banca **protegge meglio** il caso «5 o più gol» (+2,00 contro +1,40), perché l'importo è quello giusto al centesimo.
- La banca **guadagna un po' meno** con 0-3 gol (+2,58 contro +2,75), perché rischia 4,17 € invece di 4,00.
- Con 4 gol esatti perdono entrambe: è il buco strutturale della strategia. Le proposte d'uscita esistono per questo caso.
- Nel percorso B, una volta firmato, il risultato è **-2,14 con 4 gol** e **-2,13 con 5 o più**. Il caso «0-3 gol» non esiste più, perché al 64' i gol erano già 4.

---

## 6. Le regole che Mike applica (appendice per il tecnico)

I file sono relativi alla radice del repo, codice `55b0ce0`.

| Regola | Dove |
|---|---|
| Importo d'ingresso 10,00 € | `Betfair/mike/config.py:77` (`stake`) |
| Finestra d'ingresso: da 1 ora prima del fischio | `Betfair/mike/config.py:85`; controllo `Betfair/mike/engine.py:2891-2893` |
| Quota d'ingresso fra 1,30 e 3,00 | `Betfair/mike/config.py:119-120`; `Betfair/mike/engine.py:2903-2904` |
| Denaro al miglior prezzo sufficiente («liquidita 8.02 < 10.00») | `Betfair/mike/engine.py:2907` (fattore `config.py:121`) |
| Scarto massimo 6 tick («spread 9 tick») | `Betfair/mike/config.py:124`; `Betfair/mike/engine.py:2914` |
| Banca di green-up a 2 tick, appoggiata («take-profit resting») | `Betfair/mike/config.py:125,128`; `Betfair/mike/engine.py:3211`; prezzo `engine.py:419` (`green_target`) |
| Ultimo ingresso 10 minuti prima del fischio, poi «TIENE FINO AL FISCHIO» | `Betfair/mike/config.py:141`; `Betfair/mike/engine.py:2894-2895, 3107-3122` |
| Al passaggio in gioco: uscita a +2 tick | `Betfair/mike/engine.py:3057`; `config.py:164` |
| Uscita al fischio appoggiata per 180 s | `Betfair/mike/config.py:165`; `Betfair/mike/engine.py:3417, 3602-3607` |
| Finestra scaduta: annullo e copertura forzata («uscita non abbinata in 3'») | `Betfair/mike/engine.py:3506-3511` |
| Forma della copertura, di serie banca Under 4,5 | `Betfair/mike/config.py:204-212` (`cover_form`); `Betfair/mike/engine.py:461` (`cover_form`) |
| Importo della banca Under 4,5: X = fattore × perdita / (1 − commissione) | `Betfair/mike/engine.py:448-458` (`cover_residual_lay`); fattore 1,2 `config.py:188` |
| Banca Under 4,5: ordine e limite a 2 tick («BANCA U4.5 X=12.63 best=1.33 lim=1.35 buf=2t») | `Betfair/mike/engine.py:3951, 3975-3987`; margine `config.py:249` |
| Punta Over 4,5 (forma vecchia): X = fattore × S / ((q − 1)(1 − c)) | `Betfair/mike/engine.py:429-433` (`cover_size`), `436-446` (`cover_residual`), ordine `3858-3859` |
| Importo esatto al centesimo, bancata mai legalizzata | `Betfair/mike/engine.py:515-538` (`cover_legal_size`); `config.py:213-215` |
| Regola .it della puntata: minimo 2,00, passo 0,50 (arrotondato per difetto) | `Betfair/stream/live_order_build.py:41, 160-172` |
| Uscita in perdita a modello: chiudere se «chiudendo ora» ≥ «tenere» − premio | `Betfair/mike/engine.py:1400-1438` (`loss_exit_model`); decisione `4180-4194` |
| Premio = 10 % × P(4 gol esatti) × perdita massima | `Betfair/mike/engine.py:1426`; `config.py:287` |
| Uscite manuali di serie: si propone, non si esegue | `Betfair/mike/config.py:263` (`uscite_automatiche` = falso); proposta `Betfair/mike/engine.py:2759-2809` |
| La proposta decade quando la strategia non vuole più uscire | `Betfair/mike/engine.py:2704-2706, 2735` |
| La firma dell'utente esegue la decisione con i prezzi di adesso | `Betfair/mike/engine.py:2745-2758`; richiesta `Betfair/mike/service.py:3388-3410` (`_request_approva_uscita`) |
| Chiusura tutto-o-niente ridotta al denaro disponibile (12,44 → 3,00) | `Betfair/safe_strategy/execution.py:720-728` (`size_capped_from`); esito «non abbinato (tutto o niente)» `Betfair/mike/service.py:641-653` |
| Chiusura del resto, poi «PIATTA» | `Betfair/mike/engine.py:4247-4250` |
| Linea decisa dai gol (mercato 3,5 chiuso al 4° gol) | `Betfair/mike/service.py:4609` |
| Regolamento: «mercato chiuso» → «regolato T=4», commissione per mercato | `Betfair/mike/engine.py:2821-2837`; `_net` `882-883`; `net_pnl_by_total` `886-894` |
| Regola Betfair del banco (al centesimo per scommessa e per mercato) | `Betfair/stream/backtest/banco_comune.py:1113-1135` |
| Etichette dell'app | `frontend/src/lib/mike.ts:1374-1424` (Mike), `frontend/src/lib/tradeStatus.ts:431-481` (comuni); stati `mike.ts:642-660` |
| Scenari del replay | `Betfair/mike/tools/replay_registrazioni.py:109-188` |

---

## 7. Cosa non ho potuto verificare

1. **Dove esattamente 4,21 diventa 4,00 nel percorso C.** Mike manda 4,21 (`exact_sizes` acceso) e il banco abbina 4,00. La regola .it (passo 0,50 arrotondato per difetto) è in `live_order_build.py:168`. Non ho seguito riga per riga il percorso del runner paper sul canale fino a quel punto. In live, con il place-and-trim, l'importo potrebbe entrare esatto: non l'ho provato.
2. **Il prezzo della chiusura in B.** Il referto ufficiale registra 4 abbinamenti su 3 ordini, con prezzi 1,33, 1,34, 1,35 e 1,71. Quindi il banco ha abbinato la banca Over 4,5 in due pezzi, a 1,34 e a 1,35. Nella riga di Mike il prezzo medio è 1,35. Il risultato non cambia: con 4 gol una banca vinta incassa l'importo, qualunque sia la quota. Non ho scomposto i due pezzi.
3. **L'allarme «flusso fermo» sul mercato 4,5 alle 18:47:15** (fermo «da 2.805 s», cioè dalle 18:00:30 circa) e la scritta «POSIZIONE SCOPERTA». Nello stesso intervallo il motore vede le quote del 4,5 cambiare e continua a proporre uscite con quei prezzi. Non ho indagato perché il controllo del flusso consideri fermo quel mercato. Per l'utente è un allarme rosso che la cronaca non giustifica: va chiarito a parte.
4. **L'orario del regolamento** (20:04:17) è quello del banco, che fa girare il servizio 10 minuti dopo l'ultimo prezzo. In produzione il regolamento arriva quando Betfair chiude il mercato: non è misurato qui.
5. **Le probabilità del modello** (P4, «tenere») le ho riportate come le scrive il motore. Non ho ricontrollato il modello. Manca lo storico primo tempo → finale (dato «NON ESERCITABILE» dichiarato dal banco), quindi le decisioni usano solo il modello. Dopo il 4° gol la probabilità del mercato non c'è più, perché il 3,5 è chiuso.
6. **La riga di diario `canale_inviato`** non ha un'etichetta propria per Mike in `mike.ts`. Non ho verificato come la mostra l'app (probabilmente con la resa generica).
7. **Tutto è paper sul banco** (runner paper sul canale). Il comportamento live di Betfair (ritardi reali, liquidità vera) non è verificabile da una registrazione.
