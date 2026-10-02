# Sistema - Capitolo 4b: i fili diretti fra i programmi (schede)

Schema: `04b_canali_fra_programmi.html` (sorgente `04b_canali_fra_programmi.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`, sezioni C e F.

Schede dell'inventario usate: A-19, C-9, C-15 ... C-21, F-8.

Come si legge: gli stessi fili del capitolo 4a, ma fra programmi. Lo scanner manda le sue righe ai
bot; i bot mandano gli ordini al runner e ne ricevono gli esiti. Regola: «una fonte, un lettore»
(ogni programma apre un solo collegamento per fonte).

---

## Scanner

**Cosa fa**
- Pubblica sul 47336 le righe di quote e punteggi.

**Quando**
- Al massimo ogni 2,5 s per partita, solo se la riga e' cambiata.

**Numeri**
- 4 lettori: Mike, Safe, Omega, runner calcio (solo i punteggi).

**Esempio con le cifre**
- Il Over 4,5 passa da 6,40 a 5,80: Mike lo riceve dal filo entro 2,5 s, senza leggere il
  database.

**Cosa vedi nell'app**
- Le stesse quote nella Control Room.

**Se qualcosa va storto**
- Filo giu': i bot rileggono le righe dal database (Mike ogni 4 s, Safe ogni giro di 2 s).

**Per il tecnico**
- C-9 `Betfair/safe_strategy/service.py:2457`; C-15 `Betfair/safe_strategy/canale_scan.py:312`.

## Mike

**Cosa fa**
- Legge le righe dello scanner dal 47336; manda al runner solo gli ordini in prova (paper);
  legge dal runner il conto.

**Quando**
- A ogni giro (1 s).

**Numeri**
- Con il filo che copre tutte le partite, rilegge le righe dal database solo ogni 10 s invece che
  ogni 4 s.

**Esempio con le cifre**
- Mike in prova punta 2,00 EUR sull'Under: l'ordine va sul 47331 col nome «mike».

**Cosa vedi nell'app**
- Pagina di Mike.

**Se qualcosa va storto**
- Runner giu' in prova: l'ordine viene rifiutato («senza runner»).

**Per il tecnico**
- C-15 `Betfair/mike/service.py:7017`; C-17 `Betfair/mike/porta_ordini.py:36`; C-18
  `Betfair/mike/service.py:6763`.

## Bot Safe

**Cosa fa**
- Legge le righe dal 47336; manda gli ordini calcio al 47331 e quelli tennis al 47332; legge gli
  esiti degli ordini dal runner.

**Quando**
- A ogni giro (2 s) e subito quando arriva una sveglia.

**Numeri**
- Prima scelta il filo; poi la coda nel database (capitolo 7).

**Esempio con le cifre**
- Safe banca 5,00 EUR a 1,30: l'ordine va sul 47331 col nome «safe»; l'esito torna sul filo.

**Cosa vedi nell'app**
- Pagina Safe.

**Se qualcosa va storto**
- Filo giu': coda nel database.

**Per il tecnico**
- C-15 `Betfair/safe_strategy/bot_service.py:9273`; C-17 `Betfair/safe_strategy/porta_ordini.py:75`;
  C-19 `Betfair/safe_strategy/porta_ordini.py:76`.

## Omega

**Cosa fa**
- Legge le righe dal 47336; manda gli ordini al 47331 col nome «omega»; legge gli esiti.

**Quando**
- A ogni giro (20 s).

**Numeri**
- Interruttore degli ordini sul filo acceso nel `.env`.

**Esempio con le cifre**
- Il 02/10 all'avvio il registro di Omega dice «canale di comando ... non disponibile»: il runner
  non era ancora pronto.

**Cosa vedi nell'app**
- Pagina Omega.

**Se qualcosa va storto**
- Filo giu': coda nel database.

**Per il tecnico**
- C-15 `Betfair/omega/omega_service.py:759`; C-17 `Betfair/omega/porta_ordini.py:48`; C-18
  `Betfair/omega/omega_service.py:790`.

## Runner calcio

**Cosa fa**
- Riceve gli ordini dei bot sul 47331, li controlla e li piazza; pubblica gli esiti.

**Quando**
- Subito: ogni ordine sveglia il motore degli ordini.

**Numeri**
- Legge anche i punteggi dello scanner dal 47336.

**Esempio con le cifre**
- Arriva l'ordine di Safe: il runner controlla modo, freno e minimi (1,00 EUR) e lo piazza.

**Cosa vedi nell'app**
- Ordini nella pagina di trading.

**Se qualcosa va storto**
- Runner giu': i bot passano alla coda nel database (che lo stesso runner leggera' quando torna).

**Per il tecnico**
- C-4, C-16 `Betfair/stream/scores/scan_feed.py:138`; F-4.

## Runner tennis

**Cosa fa**
- Riceve sul 47332 gli ordini di Safe tennis; ospita i 4 bot tennis.

**Quando**
- Subito.

**Numeri**
- Pubblica le posizioni dei bot tennis.

**Esempio con le cifre**
- Safe tennis punta 2,00 EUR: l'ordine va sul 47332.

**Cosa vedi nell'app**
- Pagine tennis.

**Se qualcosa va storto**
- Ripiego sulla coda tennis.

**Per il tecnico**
- C-5, C-19.

## Ponte tennis

**Cosa fa**
- Legge dal 47332 le posizioni dei bot tennis e le rilancia sul suo 47337 per lo schermo.

**Quando**
- Quando il runner tennis le pubblica.

**Numeri**
- Un solo collegamento al 47332.

**Esempio con le cifre**
- Il registro del 02/10 mostra il ponte agganciato a `/lettore/tennis_bot_posizioni`.

**Cosa vedi nell'app**
- Pannello bot tennis.

**Se qualcosa va storto**
- Il registro del 02/10 mostra un primo tentativo fallito (runner tennis non ancora pronto) e poi
  l'aggancio.

**Per il tecnico**
- C-20 `Betfair/stream/tennis_live/canale_bot_tennis.py:107`.

## Frecce

- Scanner -> Mike, Safe, Omega: righe ogni 2,5 s (porta 47336).
- Scanner -> runner calcio: punteggi (porta 47336, passa sopra lo schema).
- Mike -> runner calcio: ordini in prova e lettura del conto (porta 47331).
- Safe -> runner calcio: ordini ed esiti (47331).
- Omega -> runner calcio: ordini ed esiti (47331).
- Safe -> runner tennis: ordini Safe tennis (47332).
- Runner tennis -> ponte: posizioni dei bot tennis (47332 letto dal ponte, rilanciato sul 47337).

## Punti da decidere

1. Mike vero (live) non usa il filo: va diretto a Betfair (capitolo 7). Le altre strade passano dal
   runner.

## Punti non chiariti

1. Non misurato quanti messaggi passano sui fili: i registri non li contano.
