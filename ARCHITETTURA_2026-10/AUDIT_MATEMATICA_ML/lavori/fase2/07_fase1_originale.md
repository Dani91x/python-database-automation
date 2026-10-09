# 07 - RIEPILOGO PER L'UTENTE (audit della matematica, 09/10/2026)

Cosa abbiamo fatto: controllato in sola lettura tutti i calcoli del progetto (oltre 190 voci d'inventario: previsioni Poisson,
modelli ML, matematica dei bot e degli ordini, tennis, statistiche in-play, report, schermate, funzioni del database),
rifatto a mano i conti con piccoli programmi di prova, e misurato la qualita' delle previsioni su 1.519 partite vere
(21 settembre - 7 ottobre) confrontandole con le quote dei bookmaker. Nessun file del progetto e' stato toccato, nessun
ordine piazzato, nessun bot avviato.

## La risposta in tre righe
1. **I conti che muovono i soldi sono giusti**: green-up, profitti e perdite, commissione, puntate, scala delle quote.
   C'e' un solo errore con soldi veri: il dutching "variabile" sul lato LAY piazza puntate BACK (da bloccare subito).
2. **I numeri che dicono "qui c'e' valore" sono piu' deboli del mercato**: le quote dei bookmaker prevedono meglio
   sia del nostro Poisson sia del nostro ML, e il modello del tennis guarda solo il punteggio dei giochi.
3. **Manca un termometro**: nessuno misura ogni settimana se le previsioni sono buone; per questo i problemi del punto 2
   non si vedevano.

## 1. Catena Poisson

| Domanda | Risposta | Perche', in parole semplici |
|---|---|---|
| Siamo al miglior livello matematico possibile? | **No** | Le formule sono giuste (le abbiamo rifatte in tre modi diversi: stessi numeri). Ma il modello usa solo le partite giocate della stagione in corso e non guarda le quote. Risultato misurato: le quote sbagliano meno del nostro Poisson in modo netto e sicuro (errore medio piu' basso di circa il 7% sull'1X2). Abbiamo controllato che le quote usate nel confronto fossero disponibili PRIMA della nostra previsione: lo erano, il confronto e' onesto. |
| Abbiamo omesso qualcosa? | **Si'** | Mancano: le quote come punto di partenza; la forza degli avversari affrontati; la memoria della stagione precedente (nelle prime 5 giornate non c'e' previsione); una misura continua della qualita'; un valore di correlazione dei gol stimato per quasi tutte le leghe (si usa un numero fisso). |
| Si puo' migliorare? | **Si'** | Le probabilita' grezze sono troppo "sicure di se'" (dicono 17% dove succede 33%): si corregge con pesi della forma meno estremi. La calibrazione settimanale aiuta, ma davvero solo sull'Over 2.5. |
| Sono le migliori pratiche? | **In parte** | Il motore "tattico" e' quello della letteratura (Dixon-Coles con memoria che sfuma nel tempo). Il motore principale, quello che leggono i bot, e' piu' semplice. |

## 2. Catena ML

| Domanda | Risposta | Perche' |
|---|---|---|
| E' al massimo livello possibile? | **No** | La costruzione e' fatta bene (niente "sbirciate nel futuro" nella forma delle squadre, validazione in ordine di tempo). Ma il modello che arriva in produzione non aggiunge niente alle quote, e su Over 2.5 e Goal/NoGoal non fa meglio di chi dice sempre "la media della lega". |
| Abbiamo omesso qualcosa? | **Si'** | Non si confronta mai il modello con le quote; il "cancello" che decide se un modello e' affidabile lo confronta con il lancio di una moneta invece che con la media della lega, e decide su campioni di circa 110 partite (troppo pochi: passa e boccia per caso). Le quote usate per addestrare non hanno l'orario. Il 13% delle previsioni "pre-partita" e' stato generato a partita gia' iniziata (partite notturne). |
| Si puo' fare meglio? | **Si'** | Cancello onesto, piu' dati di prova, calibrazione adatta ai campioni piccoli, riaddestrare anche sugli ultimi mesi (oggi esclusi). |
| Ci sono pratiche non usate che migliorano? | **Si'** | Confronto fisso con le quote, misura della deriva nel tempo, versioni dei dati tracciate, migliori indicatori di forza (Elo con fattore campo e scarto reti). Nota: Omega, Mike e Safe NON usano questo ML; lo usano lo scalper calcio, il foglio Quant Fund, i consigli in UI e le statistiche. |

## 3. Componenti matematici dei bot, della UI e dei report

| Domanda | Risposta | Perche' |
|---|---|---|
| Sono al massimo livello? | **In parte** | Esecuzione giusta: green-up, P&L back e lay, commissione sul guadagno netto per mercato, scala dei prezzi Betfair, conversione sterline-euro. Sotto il livello: il tennis di Safe calcola la probabilita' solo dal punteggio dei giochi (ignora i punti del game e chi e' piu' forte), l'atlante dei gol vecchio (v3) e' ancora usato da Theta, Mike prende sempre la stima piu' alta tra due. |
| Si puo' fare meglio? | **Si'** | Un solo modo di arrotondare commissione e quote in tutti i bot; un metodo migliore per togliere il margine del bookmaker (misurato); tennis con i dati di servizio dei giocatori. |
| Abbiamo omesso qualcosa? | **Si'** | Lo stop giornaliero conta i guadagni prima della commissione (scatta tardi); regole .it della documentazione Betfair (vincita massima 10.000 EUR, minimo 2 EUR) non gestite o in contrasto con il codice (che usa 1 EUR: da verificare con una prova vera). |
| E' la soluzione migliore? | **Per eseguire si', per decidere no** | Dove il numero decide se entrare, l'informazione e' inferiore al mercato; dove il numero esegue, i conti tornano. Le schermate mostrano a volte numeri diversi per la stessa cosa (drawdown, ROI dei lay, lordo/netto). |

## 4. Arrivano bene a bot, UI, previsioni e consigli?
In gran parte si': unita' coerenti (probabilita' sempre tra 0 e 1, gol attesi coerenti), nessun campo letto con il
nome sbagliato. Tre punti deboli: (1) nessun bot controlla quanto e' vecchia la previsione che usa; (2) un bot non sa
se i gol attesi vengono dal motore tattico o dal Poisson; (3) il pannello di dutching "variabile" mostra una
ripartizione diversa da quella che il server piazza.

## 5. Le prime 10 azioni (in ordine)
1. **Bloccare il dutching "variabile" sul lato LAY** e controllare nello storico se e' mai stato usato in live (D1).
2. **Safe tennis** (D2, CORRETTO dal coordinatore il 09/10): gli ingressi seguono le regole dell utente e non usano il modello; il modello entra solo nel controllo prima di incassare (gravita media). Il bot E certificato: replay del 09/10 18/18 OK, 0 violazioni. Vedi la correzione in fondo a 05.
3. **Accendere un termometro settimanale delle previsioni** (Poisson, tattico, ML, quote; serve il tuo permesso, D19): e' la base di ogni altro miglioramento.
4. **Allineare l'anteprima del dutching al server** e aggiungere le guardie contro valori non numerici (06 n.2, n.6).
5. **Cancello ML onesto** (media della lega come riferimento, campioni piu' grandi): cambia lo stake della traccia ML (D13).
6. **Previsioni delle partite notturne prima del fischio**, o marcate come tardive (D20).
7. **Stop giornaliero al netto della commissione** (D3).
8. **Verificare con una prova vera il minimo di puntata .it** e usare un solo valore in UI e motore (D16).
9. **Poisson migliore per Mike** (pesi della forma, memoria della stagione precedente, correlazione stimata per lega, una sola calibrazione), passando dal replay di certificazione (D4).
10. **Atlante v4 al posto del v3 in Theta** e media pesata al posto del massimo in Mike (D6, D7).

## Dove leggere i dettagli
`05_ERRORI_DI_PROGETTAZIONE.md` (tutti i reperti per gravita': 4 ALTI, nessun CRITICO), `06_PIANO_MIGLIORAMENTI.md`
(32 proposte con costo e misura), `DECISIONI_PER_L_UTENTE.md` (23 decisioni), `01`-`04` per le catene, `00` per
l'inventario completo. Limiti: misure su 17 giorni; modelli ML del cloud non scaricati; regole Betfair .it non provate
con ordini veri; vigenza delle funzioni SQL dedotta dai nomi dei file.
