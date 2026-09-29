# Inventario delle logiche di MIKE - istruzioni comuni per chi legge il codice

Ordine dell'utente (29/09/2026): «voglio capire esattamente OGNI SINGOLA LOGICA dei bot. Lo schema di
Mike deve essere estremamente dettagliato e deve spiegare A UN NON TECNICO come funziona il bot,
senza tralasciare NULLA. Dopodiche' ti diro' cosa modificare».

L'utente e' un trader esperto di Betfair, NON un programmatore. Da questo inventario si costruiranno
gli schemi navigabili (archify) e la spiegazione finale. Se una logica manca qui, manchera' nello
schema: l'esaustivita' e' il criterio numero uno.

## Regole di lettura
1. SOLA LETTURA. Non modificare NESSUN file del repo tranne il TUO file di inventario. Non eseguire
   test, replay, script, `.bat`, comandi git che scrivono. Non toccare il DB. Si legge e si scrive.
2. Leggi il codice VERO riga per riga nel tuo intervallo, tutto, senza saltare funzioni «di servizio».
   Non fidarti dei commenti: se il commento dice una cosa e il codice ne fa un'altra, vale il codice
   e la differenza va scritta nella sezione «Cose strane».
3. Ogni numero (soglia, quota, importo, secondi, tentativi, percentuale) va riportato col suo VALORE
   vero di oggi e da dove viene (costante nel codice, parametro di `config.py`, variabile d'ambiente,
   parametro salvato nel database e modificabile dalla UI). Se un valore ha un default e puo' essere
   cambiato, scrivi entrambi.
4. Niente interpretazioni di comodo: se non sei sicuro di cosa fa un ramo, scrivilo in «Non ho capito».

## Formato del file (markdown, italiano, parole semplici)
Per OGNI logica una scheda:

### <numero>. <titolo in parole semplici>
- **Cosa fa**: una o due frasi che capisce chi non programma. Vietato il gergo: niente «funzione»,
  «dizionario», «flag», «callback», «thread». Usa: punta (back), banca (lay), quota, importo,
  abbinato, in coda, ritirato, copertura, chiusura, profitto bloccato, esposizione.
- **Quando scatta**: le condizioni esatte, tutte, con i numeri.
- **Cosa succede dopo**: ordine piazzato / ritirato / niente / stato che cambia / avviso.
- **Numeri**: elenco dei valori coinvolti con l'origine.
- **Esempio**: un caso concreto con cifre (quota, importo, risultato in euro).
- **Cosa vede l'utente**: riga, avviso o niente (se lo sai dal codice).
- **Dove**: `file:riga` della funzione e dei rami principali.
- **Paper o live**: se il comportamento cambia fra soldi finti e soldi veri, come.

In coda al file, quattro sezioni obbligatorie:
- **Glossario**: ogni nome interno che compare (stati, ruoli delle gambe, nomi degli eventi) con la
  traduzione in parole semplici.
- **Differenze dalla Costituzione**: leggi `Betfair/mike/COSTITUZIONE_MIKE.md` per la parte che
  riguarda la tua area e scrivi ogni punto in cui il codice fa diversamente (paragrafo della
  Costituzione, cosa dice, cosa fa il codice, `file:riga`). Non giudicare e non correggere: elenca.
- **Cose strane**: codice morto, rami irraggiungibili, numeri incoerenti fra due punti, commenti che
  contraddicono il codice, casi non gestiti.
- **Non ho capito / non ho letto**: tutto cio' che non hai potuto leggere o capire. Un inventario
  che non dichiara i suoi buchi non e' accettato.

In testa al file: intervallo letto (file e righe), numero di schede, e l'elenco di TUTTE le funzioni
del tuo intervallo con accanto il numero della scheda che le copre (nessuna funzione senza scheda).
