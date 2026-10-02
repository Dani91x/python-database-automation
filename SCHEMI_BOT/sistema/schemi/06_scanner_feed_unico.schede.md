# Sistema - Capitolo 6: lo scanner, il feed unico di quote e punteggi (schede)

Schema: `06_scanner_feed_unico.html` (sorgente `06_scanner_feed_unico.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`, sezioni B, C, D, E.

Schede dell'inventario usate: B-9, B-10, B-11, C-9, C-15, D-7, D-8, D-9, E-1 ... E-10.

Come si legge: lo scanner e' un unico programma che raccoglie quote e punteggi per tutti. Entra da
sinistra (Betfair), esce a destra: sul filo 47336 per Mike, Safe e Omega, nel database per gli
altri.

---

## Betfair linea continua

**Cosa fa**
- Manda allo scanner i prezzi dei mercati seguiti.

**Quando**
- In diretta, raggruppati a 1 s.

**Numeri**
- Fino a 4 linee da 180 mercati (720 mercati), con un solo livello di prezzo.

**Esempio con le cifre**
- Dalle 16:25 alle 17:16 lo scanner ha aperto 14 linee con successo (comprese le riaperture).

**Cosa vedi nell'app**
- Quote vive nella Control Room.

**Se qualcosa va storto**
- Un mercato senza prezzi da 20 s passa alle domande (scheda successiva).

**Per il tecnico**
- B-9 `Betfair/safe_strategy/stream.py:81`, `Betfair/safe_strategy/stream.py:82`, `Betfair/safe_strategy/stream.py:265`.

## Betfair domande

**Cosa fa**
- Risponde allo scanner: elenco partite, punteggi, cronologia, prezzi di ripiego.

**Quando**
- Elenco ogni 5 minuti; punteggi ogni 2 s; cronologia ogni 30 s; ripiego da 10 a 60 s.

**Numeri**
- Ripiego calcio: 10 s se la partita e' «calda», 20 s se in gioco, 60 s altrimenti. Tennis: 10 s in
  gioco, 60 s altrimenti.

**Esempio con le cifre**
- Dalle 17:11:40 alle 17:16:40: 1 passaggio al ripiego e 1 rientro sulla linea; 151 avvisi
  «quote assenti».

**Cosa vedi nell'app**
- Avviso «Feed unico in ripiego» quando succede.

**Se qualcosa va storto**
- Dopo un errore dell'elenco, nuovo tentativo dopo 30 s.

**Per il tecnico**
- B-10 `Betfair/safe_strategy/service.py:120`, `Betfair/safe_strategy/service.py:132`; B-11
  `Betfair/safe_strategy/scanner.py:535`.

## Scanner

**Cosa fa**
- Sceglie le partite (esito finale di calcio e tennis, da 6 ore fa a 14 ore avanti, fino a 1000
  mercati), aggiunge i mercati dove i bot hanno soldi, unisce quote e punteggi in una riga per
  partita.

**Quando**
- Giro ogni 0,5 s.

**Numeri**
- 40 partite seguite alle 17:16 del 02/10.

**Esempio con le cifre**
- Mike ha una posizione sull'Over 4,5 di una partita che lo scanner non seguiva: lo scanner la
  aggiunge al giro successivo.

**Cosa vedi nell'app**
- Stato dello scanner nella Control Room.

**Se qualcosa va storto**
- Se cade, nessun bot riceve quote nuove finche' il guardiano non lo riaccende.

**Per il tecnico**
- E-1 `Betfair/safe_strategy/service.py:431`; E-3 `Betfair/safe_strategy/service.py:189`; E-7.

## Filo 47336

**Cosa fa**
- Porta le righe dello scanner in diretta a chi le ascolta.

**Quando**
- Al massimo ogni 2,5 s per partita; stato ogni 10 s.

**Numeri**
- 3 bot lo leggono (piu' il runner calcio per i punteggi e la Control Room).

**Esempio con le cifre**
- Cambia la quota: la riga esce sul filo; Mike la riceve senza leggere il database.

**Cosa vedi nell'app**
- Control Room.

**Se qualcosa va storto**
- I lettori tornano a leggere il database.

**Per il tecnico**
- C-9 `Betfair/safe_strategy/service.py:2457`, `Betfair/safe_strategy/canale_scan.py:69`.

## Righe dello scanner

**Cosa fa**
- Copia nel database delle stesse righe.

**Quando**
- Solo righe cambiate; quote al massimo ogni 2,5 s per partita.

**Numeri**
- 68 scritture al minuto.

**Esempio con le cifre**
- Ultimo giro registrato: «pubblicate 1 righe, rimosse 0 (monitorati 40)».

**Cosa vedi nell'app**
- Le pagine dei bot quando il filo e' giu'.

**Se qualcosa va storto**
- Righe vecchie: i bot le riconoscono dall'ora e non le usano.

**Per il tecnico**
- D-8 `Betfair/safe_strategy/db.py:198`; tabella `safe_strategy_scan`.

## Stato dello scanner

**Cosa fa**
- Una riga con la salute del feed (linee, ripieghi, chiamate punteggi).

**Quando**
- Ogni 10 s.

**Numeri**
- 5 scritture al minuto nel minuto misurato.

**Esempio con le cifre**
- La riga contiene anche il conto delle chiamate dei punteggi a Betfair.

**Cosa vedi nell'app**
- Spia del feed nella Control Room.

**Se qualcosa va storto**
- Riga vecchia = scanner fermo.

**Per il tecnico**
- `Betfair/safe_strategy/service.py:2930`; tabella `safe_strategy_status`; B-17.

## Posizioni dei bot

**Cosa fa**
- Dice allo scanner dove i bot hanno soldi (Omega, Safe, runner calcio, tennis) e quali partite
  segue Mike.

**Quando**
- Una domanda unica ogni 10 s; partite di Mike ogni 10 s.

**Numeri**
- 6 + 6 letture al minuto.

**Esempio con le cifre**
- Posizione aperta di Safe su una partita fuori finestra: lo scanner la segue lo stesso.

**Cosa vedi nell'app**
- Niente di diretto.

**Se qualcosa va storto**
- Se la domanda unica non esiste nel database, 6 letture separate e nuova prova dopo 5 minuti.

**Per il tecnico**
- E-6 `Betfair/safe_strategy/db.py:416`, `Betfair/safe_strategy/service.py:1951`; D-9.

## Mike

**Cosa fa**
- Legge le righe dal filo; dal database solo come controllo.

**Quando**
- Righe dal database ogni 10 s se il filo copre tutte le sue partite, altrimenti ogni 4 s.

**Numeri**
- 14 letture al minuto delle righe dal database.

**Esempio con le cifre**
- Vedi capitolo 4b.

**Cosa vedi nell'app**
- Pagina di Mike.

**Se qualcosa va storto**
- Righe dal database.

**Per il tecnico**
- C-15 `Betfair/mike/service.py:7017`; D-11.

## Bot Safe

**Cosa fa**
- Legge le righe dal filo; il filo lo sveglia quando arriva un prezzo.

**Quando**
- A ogni giro; dal database ogni 10 s se il filo e' acceso.

**Numeri**
- 10 letture al minuto (righe e stato).

**Esempio con le cifre**
- Vedi capitolo 4b.

**Cosa vedi nell'app**
- Pagina Safe.

**Se qualcosa va storto**
- Righe dal database a ogni giro.

**Per il tecnico**
- C-15 `Betfair/safe_strategy/bot_service.py:9273`.

## Omega

**Cosa fa**
- Legge le righe dal filo (stesso collegamento del feed unico).

**Quando**
- A ogni giro.

**Numeri**
- 0 letture delle righe dal database nel minuto misurato.

**Esempio con le cifre**
- Il registro di Omega del 02/10: «righe dello scanner dal client CONDIVISO col feed unico».

**Cosa vedi nell'app**
- Pagina Omega.

**Se qualcosa va storto**
- Righe dal database con memoria di 2 s.

**Per il tecnico**
- C-15 `Betfair/omega/omega_service.py:759`.

## Altri lettori

**Cosa fa**
- Runner calcio (punteggi per le partite seguite), scalper (scelta delle partite), ponte tennis
  (partite dei bot tennis) leggono le righe dal database.

**Quando**
- Runner calcio con memoria di 1 s (10 s col filo vivo); scalper ogni 15 s; ponte a ogni giro con
  un bot acceso.

**Numeri**
- Runner calcio 10 letture al minuto.

**Esempio con le cifre**
- Il runner usa il punteggio dello scanner; chiede a Betfair solo se la riga e' piu' vecchia di
  15 s.

**Cosa vedi nell'app**
- Punteggi nelle pagine di trading.

**Se qualcosa va storto**
- Runner: punteggi chiesti a Betfair.

**Per il tecnico**
- E-9 `Betfair/stream/scalper/scalper_service.py:110`, `Betfair/stream/tennis_live/tennis_db.py:152`;
  D-7; B-6.

## Frecce

- Linea continua -> scanner: quote ogni 1 s.
- Domande -> scanner: punteggi ogni 2 s (piu' elenco ogni 5 minuti e ripiego).
- Scanner -> filo 47336: righe ogni 2,5 s.
- Scanner -> righe dello scanner: 68 scritture al minuto.
- Scanner -> stato: ogni 10 s.
- Scanner -> posizioni dei bot: legge ogni 10 s (tratteggiata: e' una lettura).
- Filo -> Mike, Safe, Omega: righe in diretta.
- Righe -> altri lettori: dal database.

## Punti da decidere

1. Lo scanner e' il feed di TUTTI i bot ma vive dentro il programma della strategia Safe.
2. Nel minuto misurato 151 avvisi di «quote assenti» in 5 minuti: alcuni mercati restano senza
   prezzi dalla linea continua.

## Punti non chiariti

1. Non verificato quali mercati restano senza quote e perche'.
