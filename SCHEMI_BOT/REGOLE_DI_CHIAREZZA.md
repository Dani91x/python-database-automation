# Regole di chiarezza per gli schemi e le guide dei bot

Ordine dell'utente (29/09/2026): gli schemi devono essere **dettagliati ma estremamente chiari anche
a un non tecnico**. L'utente e' un trader esperto di Betfair, non un programmatore: deve poter
indicare un punto dello schema e dire «qui voglio cambiare questo».

Valgono per ogni schema archify, ogni scheda e ogni guida in `SCHEMI_BOT/`.

## Parole
1. Solo parole del trading e dell'uso comune: punta, banca, quota, importo, abbinato, in coda,
   ritirato, copertura, chiusura, profitto bloccato, esposizione, fischio d'inizio, gol, sospeso.
2. Vietati i nomi interni del codice nel testo che l'utente legge (nomi di funzioni, stati in
   inglese, parametri). Se un nome interno serve per ritrovare il punto nel codice, va in piccolo in
   fondo alla scheda, alla voce «Per il tecnico».
3. Vietato il gergo informatico: funzione, flag, thread, callback, cache, polling, payload, retry.
   Si dice: «controllo», «interruttore», «memoria temporanea», «ricontrolla ogni 5 secondi»,
   «riprova».
4. Una sigla si scrive per esteso la prima volta.

## Frasi
5. Una frase, un fatto. Soggetto sempre il bot o l'utente: «Mike punta 2,00 EUR sull'Under».
6. Ogni condizione e' una domanda a cui si risponde si' o no: «La quota e' fra 1,50 e 2,20?».
7. Ogni numero ha la sua unita': euro, secondi, minuti, tick, percentuale, quota.
8. Niente «eventualmente», «in alcuni casi», «tipicamente»: o si dice quando, o si scrive che non
   lo si sa.

## Schema
9. Un solo percorso principale da sinistra a destra (o dall'alto in basso); le deviazioni partono
   dal riquadro piu' vicino.
10. Al massimo 12 riquadri per schema. Se servono di piu', lo schema si divide in due capitoli.
11. Ogni riquadro: titolo di 2-4 parole piu' una riga che dice cosa succede li'.
12. Ogni freccia che non e' ovvia porta scritta la condizione («gol entro 10 minuti»).
13. Stessi colori per lo stesso significato in tutti gli schemi: attesa, azione, decisione,
    profitto, perdita o blocco.

## Scheda sotto lo schema (una per riquadro)
14. Ordine fisso: **Cosa fa** / **Quando** / **Numeri** / **Esempio con le cifre** /
    **Cosa vedi nell'app** / **Se qualcosa va storto** / **Per il tecnico** (file e riga).
15. L'esempio e' obbligatorio e usa cifre vere: quota, importo, risultato in euro nei due esiti.
16. Se una regola cambia fra paper e live, lo dice la scheda in una riga a parte.

## Completezza
17. Chiaro non vuol dire ridotto: ogni logica dell'inventario compare in una scheda. Cio' che non
    entra nello schema entra nelle schede sotto.
18. Cio' che non si e' capito o non si e' letto si scrive in una sezione «Punti non chiariti»: mai
    nascosto.
