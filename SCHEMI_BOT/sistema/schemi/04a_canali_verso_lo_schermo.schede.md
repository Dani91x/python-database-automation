# Sistema - Capitolo 4a: i fili diretti verso lo schermo (schede)

Schema: `04a_canali_verso_lo_schermo.html` (sorgente `04a_canali_verso_lo_schermo.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`, sezione C.

Schede dell'inventario usate: C-1 ... C-14, C-21, F-10.

Come si legge: un «canale locale» e' un filo diretto dentro il computer (tecnicamente un
WebSocket su 127.0.0.1): un programma ci pubblica le sue notizie e lo schermo le riceve subito,
senza passare dal database. Ogni programma ha la sua porta. Solo le pagine dell'app (porta 47330)
possono collegarsi. Solo i due runner accettano ordini, e solo con la chiave segreta.

---

## Runner calcio

**Cosa fa**
- Pubblica sulla porta 47331 i prezzi (ladder), gli ordini, le posizioni, il saldo, il battito e
  lo stato della linea; accetta ordini dallo schermo e dai bot.

**Quando**
- Sempre.

**Numeri**
- Prezzi ogni 0,3 s (valore impostato dall'app).

**Esempio con le cifre**
- Clicchi una quota a 2,10 nella scala prezzi: l'ordine parte sul filo 47331 e arriva al runner
  senza passare dal database.

**Cosa vedi nell'app**
- La scala prezzi del calcio, il saldo, gli ordini.

**Se qualcosa va storto**
- Filo giu': l'ordine va nella coda del database e il runner lo rilegge entro 1 s.

**Per il tecnico**
- C-4 `Betfair/stream/runner.py:2585`; C-13 `desktop/main.js:366`, `Betfair/stream/runner.py:745`.

## Runner tennis

**Cosa fa**
- Porta 47332: prezzi, ordini e posizioni del tennis; accetta ordini.

**Quando**
- Sempre.

**Numeri**
- Prezzi ogni 0,3 s.

**Esempio con le cifre**
- Ordine tennis da 2,00 EUR dallo schermo: va sul 47332 con la chiave.

**Cosa vedi nell'app**
- Pagine tennis.

**Se qualcosa va storto**
- Ripiego sulla coda tennis del database.

**Per il tecnico**
- C-5 `Betfair/stream/tennis_live/tennis_runner.py:2986`.

## Mike

**Cosa fa**
- Porta 47333: le partite di Mike, lo stato e le posizioni.

**Quando**
- A ogni giro di Mike.

**Numeri**
- Sola lettura: dallo schermo accetta solo la sveglia.

**Esempio con le cifre**
- Mike apre una posizione: la scheda della partita si aggiorna subito, senza aspettare i 15 s
  della rilettura.

**Cosa vedi nell'app**
- La pagina di Mike.

**Se qualcosa va storto**
- Filo giu': la pagina rilegge dal database ogni 15 s.

**Per il tecnico**
- C-6 `Betfair/mike/service.py:6785`.

## Omega

**Cosa fa**
- Porta 47334: stato, posizioni, attivita' e proposte di Omega.

**Quando**
- A ogni giro di Omega.

**Numeri**
- Sola lettura (piu' la sveglia).

**Esempio con le cifre**
- Omega propone una banca: la proposta appare subito.

**Cosa vedi nell'app**
- Pagina Omega.

**Se qualcosa va storto**
- Rilettura dal database ogni 15 s.

**Per il tecnico**
- C-7 `Betfair/omega/omega_service.py:8372`.

## Bot Safe

**Cosa fa**
- Porta 47335: stato, posizioni calcio e tennis (separate), attivita' e proposte.

**Quando**
- A ogni giro di Safe.

**Numeri**
- Sola lettura (piu' la sveglia).

**Esempio con le cifre**
- Safe chiude una posizione: la riga cambia subito.

**Cosa vedi nell'app**
- Pagina Safe.

**Se qualcosa va storto**
- Rilettura dal database ogni 15 s.

**Per il tecnico**
- C-8 `Betfair/safe_strategy/bot_service.py:10310`.

## Scanner

**Cosa fa**
- Porta 47336: righe di quote e punteggi (calcio e tennis separati) e stato dello scanner.

**Quando**
- Righe al massimo ogni 2,5 s per partita; stato ogni 10 s.

**Numeri**
- Lo leggono lo schermo (Control Room) e i bot (capitolo 4b).

**Esempio con le cifre**
- Gol al 63': la riga della partita esce sul filo entro 2,5 s.

**Cosa vedi nell'app**
- Control Room.

**Se qualcosa va storto**
- Lo schermo rilegge le righe dal database.

**Per il tecnico**
- C-9 `Betfair/safe_strategy/service.py:2457`, `Betfair/safe_strategy/service.py:159`.

## Ponte tennis

**Cosa fa**
- Porta 47337: stato dei 4 bot tennis, armamenti e posizioni (riprese dal runner tennis).

**Quando**
- A ogni giro del ponte (15 s) e quando arrivano posizioni dal runner tennis.

**Numeri**
- Sola lettura (piu' la sveglia).

**Esempio con le cifre**
- Armi un bot tennis: lo stato «armato» appare sul filo.

**Cosa vedi nell'app**
- Pannello dei bot tennis.

**Se qualcosa va storto**
- Rilettura dal database ogni 30 s.

**Per il tecnico**
- C-10 `Betfair/stream/tennis_live/tennis_bot_service.py:258`.

## Scalper calcio

**Cosa fa**
- Porta 47338: interruttore generale e stato delle sessioni (con profitto lordo e ordini vivi).

**Quando**
- Ogni 3 s.

**Numeri**
- Sola lettura.

**Esempio con le cifre**
- Una sessione apre un ordine: il pannello lo mostra entro 3 s.

**Cosa vedi nell'app**
- Pannello scalper e Control Room.

**Se qualcosa va storto**
- Rilettura dal database ogni 4 s (pannello scalper).

**Per il tecnico**
- C-11 `Betfair/stream/scalper/scalper_service.py:597`.

## App desktop

**Cosa fa**
- La pagina (servita sulla porta 47330) si collega direttamente a tutti i fili.

**Quando**
- Quando apri la pagina che serve.

**Numeri**
- Se un filo cade, la pagina riprova ogni 1-5 s.

**Esempio con le cifre**
- La Control Room ascolta scanner, ponte tennis, scalper e il saldo del runner calcio.

**Cosa vedi nell'app**
- Tutti gli aggiornamenti istantanei.

**Se qualcosa va storto**
- Ogni pagina ha la sua rilettura dal database come ripiego.

**Per il tecnico**
- C-14 `frontend/src/lib/localChannel.ts:62`; G-1 `desktop/main.js:25`.

## Chiave segreta

**Cosa fa**
- E' la chiave che serve per mandare ORDINI sui fili dei runner.

**Quando**
- Nuova a ogni apertura dell'app.

**Numeri**
- 32 byte casuali.

**Esempio con le cifre**
- Una pagina qualunque del computer senza chiave prova a mandare un ordine sul 47331: rifiutato e
  collegamento chiuso.

**Cosa vedi nell'app**
- Niente.

**Se qualcosa va storto**
- Senza chiave lo schermo manda gli ordini nella coda del database.

**Per il tecnico**
- C-2 `desktop/main.js:59`, `desktop/preload.js:21`; C-3 `Betfair/stream/local_channel.py:425`.

## Frecce

- Runner calcio -> app: prezzi ogni 0,3 s, ordini, saldo.
- Runner tennis -> app: prezzi tennis, ordini.
- Mike -> app: partite e posizioni.
- Omega -> app: posizioni e proposte.
- Safe -> app: posizioni e proposte.
- Scanner -> app: quote ogni 2,5 s.
- Ponte tennis -> app: bot tennis armati.
- Scalper -> app: sessioni ogni 3 s.
- Chiave -> app: data dal guscio dell'app alla pagina all'apertura.

## Punti da decidere

1. Molti fili si accendono solo con un interruttore nel file `.env` (spento di serie nel codice).
   Nel `.env` del 02/10 sono tutti accesi: un `.env` nuovo li spegnerebbe tutti.

## Punti non chiariti

1. Non verificato quante pagine sono aperte in un dato momento (ogni pagina apre i suoi fili).
