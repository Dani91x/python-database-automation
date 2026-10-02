# Sistema - Capitolo 10: dove e' il peso (schede)

Schema: `10_dove_e_il_peso.html` (sorgente `10_dove_e_il_peso.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`, sezioni D-M e I.

Schede dell'inventario usate: D-M, I-1 ... I-6.

Come si legge: i 5 programmi che chiamano di piu' il database, con lo spessore proporzionale alle
chiamate. Sotto, i file piu' grandi e i doppioni.

---

## Runner calcio

**Cosa fa**
- Rilegge di continuo coda ordini, regole di rischio e impostazioni.

**Quando**
- Circa 8 letture al secondo in tutto.

**Numeri**
- 552 al minuto (42% del totale).

**Esempio con le cifre**
- 189 coda + 168 regole + 123 impostazioni = 480 al minuto solo per «c'e' qualcosa da fare?».

**Cosa vedi nell'app**
- -

**Se qualcosa va storto**
- Database lento = ordini dalla coda presi in ritardo.

**Per il tecnico**
- D-2 ... D-5.

## Mike

**Cosa fa**
- Rilegge comandi, richieste e operazioni a ogni giro di 1 s.

**Quando**
- Ogni 1 s.

**Numeri**
- 279 al minuto (21%).

**Esempio con le cifre**
- 116 letture delle operazioni al minuto.

**Cosa vedi nell'app**
- -

**Se qualcosa va storto**
- -

**Per il tecnico**
- D-10.

## Bot Safe

**Cosa fa**
- Rilegge comandi (due volte per giro), richieste e operazioni.

**Quando**
- Ogni 2 s; richieste ogni 0,25 s con posizioni aperte.

**Numeri**
- 269 al minuto (21%).

**Esempio con le cifre**
- 53 aggiornamenti delle richieste al minuto.

**Cosa vedi nell'app**
- -

**Se qualcosa va storto**
- -

**Per il tecnico**
- D-12, D-13.

## Scanner

**Cosa fa**
- Scrive le righe delle partite.

**Quando**
- Quando cambiano.

**Numeri**
- 86 al minuto (7%).

**Esempio con le cifre**
- 68 scritture di righe al minuto.

**Cosa vedi nell'app**
- -

**Se qualcosa va storto**
- -

**Per il tecnico**
- D-8.

## Scalper calcio

**Cosa fa**
- Rilegge comandi e freno.

**Quando**
- Ogni 3 s, anche senza sessioni.

**Numeri**
- 54 al minuto (4%).

**Esempio con le cifre**
- 18 + 18 + 18.

**Cosa vedi nell'app**
- -

**Se qualcosa va storto**
- -

**Per il tecnico**
- D-17.

## Database Supabase

**Cosa fa**
- Riceve tutte queste chiamate.

**Quando**
- Sempre.

**Numeri**
- I 5 programmi qui sopra fanno 1.240 delle 1.309 chiamate al minuto (95%).

**Esempio con le cifre**
- 552 + 279 + 269 + 86 + 54 = 1.240.

**Cosa vedi nell'app**
- -

**Se qualcosa va storto**
- Se il database rallenta, rallentano tutti insieme.

**Per il tecnico**
- D-M.

## I file piu' grandi

**Cosa fa**
- Riquadro sotto lo schema: righe di codice dei file piu' grandi.

**Quando**
- Contate alla base del 02/10.

**Numeri**
- Bot Safe 10.862; Omega 8.709; Mike 7.496; motore della strategia di Mike 5.097; esecutore degli
  ordini del runner 3.991; scanner 3.444; runner calcio 3.116; motore ordini del filo 2.417; guscio
  dell'app 959.

**Esempio con le cifre**
- I tre programmi dei bot (Safe, Omega, Mike) sommano 27.067 righe.

**Cosa vedi nell'app**
- -

**Se qualcosa va storto**
- File grandi = modifiche piu' difficili da controllare.

**Per il tecnico**
- I-1.

## I doppioni

**Cosa fa**
- Riquadro sotto lo schema: cose fatte piu' volte in posti diversi.

**Quando**
- -

**Numeri**
- Rilettura degli ordini: runner (ogni 30 s), Safe, Omega, Mike e scalper, ognuno a modo suo; tre
  scritture diverse della domanda «ordini aperti / regolati».
- La decisione «l'ordine e' andato?» esiste due volte (Safe e Mike da una parte, Omega dall'altra).
- La scrittura nella coda ordini e' copiata identica tre volte (Omega, Safe, Mike).
- Quattro strade per gli ordini calcio (capitolo 7).
- Lo scanner, feed di tutti, vive dentro il programma della strategia Safe.

**Esempio con le cifre**
- Cambiare il modo di rileggere gli ordini vuol dire toccare 5 posti.

**Cosa vedi nell'app**
- -

**Se qualcosa va storto**
- Un difetto corretto in un posto resta negli altri.

**Per il tecnico**
- I-2 `Betfair/stream/reconcile_worker.py:287`, `Betfair/omega/omega_market.py:1540`, `Betfair/client.py:361`;
  I-3 `Betfair/safe_strategy/execution.py:1381`, `Betfair/omega/omega_service.py:4215`; I-4; I-5; I-6.

## Frecce

- Runner calcio -> database: 552 al minuto.
- Mike -> database: 279 al minuto.
- Safe -> database: 269 al minuto.
- Scanner -> database: 86 al minuto.
- Scalper -> database: 54 al minuto.

## Punti da decidere

1. Le riletture continue «c'e' qualcosa da fare?» del runner, di Mike e di Safe sono l'84% del
   traffico: da decidere se spostarle sui fili diretti (sveglie) gia' esistenti.
2. I doppioni della rilettura ordini e della coda.

## Punti non chiariti

1. Il peso su Betfair non e' misurabile dai registri (nessun contatore).
