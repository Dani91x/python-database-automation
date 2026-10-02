# Sistema - Capitolo 3: chi parla con Betfair, come e quanto (schede)

Schema: `03_linee_con_betfair.html` (sorgente `03_linee_con_betfair.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`, sezione B e tabella D-B.

Schede dell'inventario usate: B-1 ... B-17, F-6, F-8, F-9.

Come si legge: a sinistra la «linea continua» (Betfair spinge i prezzi da sola, senza che nessuno
chieda: si chiama stream); a destra le «domande» (il programma chiede e Betfair risponde una
volta: si chiama REST). Freccia piena = a ritmo fisso; tratteggiata = solo quando serve o di
ripiego. ATTENZIONE: i ritmi di questo capitolo vengono dal codice; i registri non contano le
chiamate a Betfair una per una (vedi «Punti non chiariti»).

---

## Betfair linea continua

**Cosa fa**
- Spinge in diretta prezzi e stato degli ordini a chi ha aperto la linea.

**Quando**
- Sempre, finche' la linea e' aperta.

**Numeri**
- Linee aperte: runner calcio (mercati + ordini), runner tennis (partite + ordini), scanner (fino a
  4 linee da 180 mercati), una linea per ogni sessione scalper.

**Esempio con le cifre**
- Il 02/10 dalle 16:25 alle 17:16 il runner calcio ha registrato 54 aperture riuscite della linea
  mercati e 48 «sottoscrizioni a caldo» (aggiunta di mercati senza chiudere la linea).

**Cosa vedi nell'app**
- Quote che si muovono senza ricaricare.

**Se qualcosa va storto**
- La linea si riapre da sola; lo scanner, nel frattempo, chiede i prezzi a domanda (capitolo 6).

**Per il tecnico**
- B-4 `Betfair/stream/runner.py:2805`; B-7 `Betfair/stream/tennis_live/tennis_runner.py:469`; B-8;
  B-9 `Betfair/safe_strategy/stream.py:418`.

## Runner calcio

**Cosa fa**
- Riceve prezzi e ordini dalla linea continua; fa anche domande a ritmo fisso.

**Quando**
- Sempre.

**Numeri**
- Saldo del conto ogni 20 s.
- Con ordini veri (LIVE): rilettura degli ordini aperti e regolati ogni 30 s.
- Catalogo dei mercati seguiti ogni 60 s (lo fa la libreria flumine).
- Punteggi chiesti a Betfair solo se la riga dello scanner manca o e' piu' vecchia di 15 s.

**Esempio con le cifre**
- Dalle 16:25 alle 17:16: 343 aggiornamenti di catalogo, 41 letture dei regolati, 33 saldi
  riletti dopo un regolamento.

**Cosa vedi nell'app**
- Saldo e ordini nella pagina di trading.

**Se qualcosa va storto**
- Se la domanda fallisce si riprova al giro dopo.

**Per il tecnico**
- B-5 `Betfair/stream/reconcile_worker.py:96`, `Betfair/stream/reconcile_worker.py:287`; B-6
  `Betfair/stream/scores/scan_feed.py:43`.

## Scanner

**Cosa fa**
- Tiene fino a 4 linee continue e fa domande per elenchi e punteggi.

**Quando**
- Sempre; giro ogni 0,5 s.

**Numeri**
- Elenco delle partite (catalogo) ogni 5 minuti.
- Punteggi ogni 2 s; cronologia degli eventi ogni 30 s.
- Prezzi a domanda solo per i mercati senza prezzi dalla linea da 20 s.

**Esempio con le cifre**
- Dalle 17:11:40 alle 17:16:40: 1 passaggio al ripiego a domanda e 1 rientro sulla linea continua.

**Cosa vedi nell'app**
- Quote e punteggi nelle pagine dei bot.

**Se qualcosa va storto**
- Capitolo 6.

**Per il tecnico**
- B-9, B-10 `Betfair/safe_strategy/service.py:120`, B-11 `Betfair/safe_strategy/service.py:223`.

## Runner tennis

**Cosa fa**
- Una linea continua per le partite tennis seguite.

**Quando**
- Sempre; senza partite non apre la linea.

**Numeri**
- Rinfresco della sessione ogni 480 s (8 minuti).

**Esempio con le cifre**
- Dalle 16:25 alle 17:16: 6 rinfreschi di sessione, nessuna partita.

**Cosa vedi nell'app**
- Pagine tennis.

**Se qualcosa va storto**
- Punteggi chiesti a Betfair solo se manca la riga dello scanner.

**Per il tecnico**
- B-7 `Betfair/stream/tennis_live/tennis_runner.py:1506`.

## Sessioni scalper

**Cosa fa**
- Ogni sessione (una per partita) fa il suo accesso e apre la sua linea.

**Quando**
- Solo con una partita armata.

**Numeri**
- Domande all'avvio (catalogo e prezzi) e all'arresto (ordini aperti e annullo).

**Esempio con le cifre**
- Il 02/10 alle 17:16 nessuna sessione era accesa: nessuna linea scalper aperta.

**Cosa vedi nell'app**
- Pannello scalper.

**Se qualcosa va storto**
- All'arresto o se cade, annulla i suoi ordini aperti.

**Per il tecnico**
- B-8 `Betfair/stream/scalper/scalper_session.py:1085`, `Betfair/stream/scalper/scalper_session.py:448`.

## Mike

**Cosa fa**
- Non ha linea continua: legge le quote dallo scanner. Chiede a Betfair solo quando serve.

**Quando**
- Ordini veri (LIVE): sempre a domanda diretta.
- Prezzi a domanda solo per le linee col flusso fermo.

**Numeri**
- Prezzi a domanda: al massimo uno ogni 10 s per mercato.
- Saldo dal filo del runner; se il filo manca, a domanda ogni 30 s.

**Esempio con le cifre**
- Dalle 16:25 alle 17:16 il registro di Mike mostra 12 «saldo riletto dopo ordine».

**Cosa vedi nell'app**
- La pagina di Mike.

**Se qualcosa va storto**
- Una domanda fallita si ripete una volta dopo un nuovo accesso.

**Per il tecnico**
- B-12 `Betfair/mike/service.py:149`; B-15 `Betfair/mike/service.py:1267`; F-8.

## Bot Safe

**Cosa fa**
- Non ha linea continua: legge lo scanner. Chiede a Betfair solo se serve.

**Quando**
- Ordini veri: a domanda solo se il filo e la coda falliscono.
- Prezzi a domanda solo se lo scanner non li ha.

**Numeri**
- Prezzi: al massimo uno ogni 10 s per mercato e 8 per giro.
- Posizione del conto: ogni 30 s per mercato, al massimo 2 mercati per giro.

**Esempio con le cifre**
- Partita senza prezzi nello scanner: Safe chiede quella partita a Betfair, poi aspetta 10 s prima
  di chiederla di nuovo.

**Cosa vedi nell'app**
- Pagina Safe.

**Se qualcosa va storto**
- Nuovo accesso e una ripetizione.

**Per il tecnico**
- B-14 `Betfair/safe_strategy/bot_service.py:759`; F-6.

## Omega

**Cosa fa**
- Non ha linea continua. Con il bot acceso chiede a ogni giro l'elenco delle partite del giorno.

**Quando**
- A ogni giro col bot acceso (20 s); sessione rinfrescata ogni 600 s.

**Numeri**
- 3 domande al minuto di elenco partite col bot acceso (una ogni 20 s).

**Esempio con le cifre**
- Il 02/10 Omega era fermo: nessun elenco chiesto.

**Cosa vedi nell'app**
- Pagina Omega.

**Se qualcosa va storto**
- Nuovo accesso e una ripetizione.

**Per il tecnico**
- B-13 `Betfair/omega/omega_service.py:8031`, `Betfair/omega/omega_market.py:140`.

## Quote tennis

**Cosa fa**
- Chiede l'elenco, il catalogo e le quote delle partite tennis del giorno, poi esce.

**Quando**
- All'apertura e ogni 30 minuti.

**Numeri**
- Catalogo a blocchi di 10 partite; quote a blocchi di 8 mercati.

**Esempio con le cifre**
- Il 02/10 alle 16:55: 27 partite scritte.

**Cosa vedi nell'app**
- Partite tennis del giorno.

**Se qualcosa va storto**
- Il giro dopo, 30 minuti piu' tardi.

**Per il tecnico**
- B-16 `betfair_tennis_odds.py:204`, `betfair_tennis_odds.py:53`, `betfair_tennis_odds.py:244`.

## Betfair domande

**Cosa fa**
- Risponde a una domanda alla volta (elenchi, prezzi, saldo, ordini).

**Quando**
- Ogni volta che un programma chiede.

**Numeri**
- Ogni programma fa il SUO accesso con il certificato .it: non c'e' una sessione condivisa.
- Nei registri del 02/10: accessi in runner calcio, runner tennis, scanner, scalper, Mike, Omega e
  2 nelle quote tennis.

**Esempio con le cifre**
- 7 programmi diversi hanno fatto un accesso fra le 16:25 e le 17:16.

**Cosa vedi nell'app**
- Niente di diretto.

**Se qualcosa va storto**
- Betfair limita il numero di linee e di chiamate: piu' accessi separati vogliono dire piu' carico.

**Per il tecnico**
- B-1 `Betfair/stream/auth.py:70`; B-2 `Betfair/client.py:95`; B-3.

## Frecce

- Linea continua -> runner calcio, scanner, runner tennis, sessioni scalper: prezzi in diretta
  (freccia piena spessa).
- Runner calcio -> domande: saldo ogni 20 s, ordini ogni 30 s (solo LIVE).
- Scanner -> domande: punteggi ogni 2 s, elenco ogni 5 minuti; prezzi di ripiego 10-60 s.
- Runner tennis -> domande: rinfresco sessione ogni 8 minuti (tratteggiata).
- Sessioni scalper -> domande: all'avvio e all'arresto (tratteggiata).
- Mike -> domande: ordini veri e solo se serve (tratteggiata).
- Safe -> domande: solo se serve o manca il feed (tratteggiata).
- Omega -> domande: elenco partite a ogni giro col bot acceso (piena).
- Quote tennis -> domande: ogni 30 minuti (tratteggiata).

## Punti da decidere

1. Ogni programma fa il suo accesso a Betfair: 7 accessi separati in un pomeriggio.
2. Omega chiede l'elenco partite a ogni giro, anche se lo scanner lo ha gia'.

## Punti non chiariti

1. Le chiamate a Betfair non sono contate: nei registri non c'e' un contatore. I ritmi qui sopra
   sono quelli scritti nel codice.
2. Due commenti del codice si contraddicono su come resta viva la sessione «a domanda» del runner
   calcio (`Betfair/stream/runner.py:2747` e `Betfair/stream/auth.py:100`).
3. Il commento di `desktop/main.js:474` dice che Mike non fa accessi propri, ma il registro di Mike
   ne mostra uno: e' l'accesso del client a domanda, usato per gli ordini veri e il saldo.
