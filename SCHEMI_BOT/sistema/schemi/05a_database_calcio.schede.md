# Sistema - Capitolo 5a: il database come postino, il calcio (schede)

Schema: `05a_database_calcio.html` (sorgente `05a_database_calcio.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`, sezione D e tabella D-M;
conteggi grezzi in `SCHEMI_BOT/sistema/MISURE_2026-10-02.md`.

Schede dell'inventario usate: D-1 ... D-14, D-19, D-M.

Come si legge: la freccia parte da chi fa la chiamata (lettura o scrittura). Il numero e' quante
chiamate in un minuto, il 02/10 dalle 17:15:40 alle 17:16:40. Una «tabella» e' un elenco nel
database (come un foglio di calcolo).

---

## Righe dello scanner

**Cosa fa**
- Una riga per partita con quote, punteggio e stato; piu' una riga di salute dello scanner.

**Quando**
- Lo scanner la scrive quando cambia qualcosa (quote al massimo ogni 2,5 s per partita).

**Numeri**
- Scritte 68 volte al minuto; lette 10 volte dal runner calcio, 14 da Mike, 10 da Safe.

**Esempio con le cifre**
- 40 partite seguite alle 17:16; nell'ultimo giro registrato lo scanner ha pubblicato 8 righe
  cambiate.

**Cosa vedi nell'app**
- Control Room e pagine dei bot.

**Se qualcosa va storto**
- Se lo scanner si ferma, le righe invecchiano: i bot vedono quote vecchie e le scartano.

**Per il tecnico**
- Tabelle `safe_strategy_scan`, `safe_strategy_status`. D-8 `Betfair/safe_strategy/db.py:198`.

## Runner calcio

**Cosa fa**
- Rilegge di continuo la coda degli ordini, le regole di rischio e le impostazioni.

**Quando**
- Circa ogni secondo, anche quando la coda e' vuota.

**Numeri**
- 552 al minuto: 480 su coda, regole e impostazioni; 62 sul resto; 10 sulle righe dello scanner.

**Esempio con le cifre**
- La coda ordini viene letta 189 volte al minuto: 3 letture al secondo (richieste nuove, sequenze
  «sotto il minimo» in prova e in live).

**Cosa vedi nell'app**
- Niente di diretto.

**Se qualcosa va storto**
- Se il database rallenta, un ordine messo in coda viene preso piu' tardi.

**Per il tecnico**
- D-2 `Betfair/stream/live_order_worker.py:3846`; D-3 `Betfair/stream/live_order_worker.py:3720`;
  D-4 `Betfair/stream/risk_engine_worker.py:1173`; D-5 `Betfair/stream/live_order_worker.py:498`.

## Scanner

**Cosa fa**
- Scrive le sue righe e il suo stato; legge le partite seguite da Mike e le posizioni dei bot.

**Quando**
- Righe quando cambiano; stato ogni 10 s; posizioni ogni 10 s.

**Numeri**
- 86 al minuto: 74 sulle sue righe e sul suo stato, 12 sulle posizioni dei bot (6 partite di
  Mike, 6 posizioni di tutti i bot).

**Esempio con le cifre**
- Ogni 10 s una domanda sola al database restituisce le posizioni aperte di tutti i bot.

**Cosa vedi nell'app**
- Niente di diretto.

**Se qualcosa va storto**
- Se la domanda unica manca, lo scanner fa 6 letture separate e riprova la domanda unica dopo 5
  minuti.

**Per il tecnico**
- D-8, D-9 `Betfair/safe_strategy/service.py:1945`; E-6 `Betfair/safe_strategy/db.py:432`.

## Mike

**Cosa fa**
- A ogni giro rilegge i comandi, le richieste e le operazioni aperte; scrive gli eventi delle
  partite.

**Quando**
- Ogni 1 s (5 s a vuoto).

**Numeri**
- 279 al minuto: 265 sulle sue tabelle, 14 sulle righe dello scanner.

**Esempio con le cifre**
- In un minuto: 116 letture delle operazioni (circa 2 al secondo), 58 dei comandi, 58 delle
  richieste, 25 scritture di eventi.

**Cosa vedi nell'app**
- Pagina di Mike.

**Se qualcosa va storto**
- Tempo massimo di attesa 20 s per lettura; un giro senza database viene saltato.

**Per il tecnico**
- D-10 `Betfair/mike/service.py:3953`, `Betfair/mike/service.py:3984`, `Betfair/mike/service.py:4087`;
  D-11.

## Bot Safe

**Cosa fa**
- A ogni giro rilegge comandi, richieste e operazioni; aggiorna le richieste e il battito.

**Quando**
- Ogni 2 s; con posizioni aperte guarda le richieste ogni 0,25 s.

**Numeri**
- 269 al minuto: 259 sulle sue tabelle, 10 sullo scanner.

**Esempio con le cifre**
- In un minuto: 81 letture delle operazioni, 53 aggiornamenti e 44 letture delle richieste, 36
  letture e 19 scritture dei comandi.

**Cosa vedi nell'app**
- Pagina Safe.

**Se qualcosa va storto**
- Tempo massimo di attesa 20 s per lettura.

**Per il tecnico**
- D-12 `Betfair/safe_strategy/bot_service.py:10581`, `Betfair/safe_strategy/bot_service.py:9864`,
  `Betfair/safe_strategy/bot_service.py:10481`; D-13.

## Omega

**Cosa fa**
- A ogni giro rilegge comandi, operazioni, richieste manuali e missioni.

**Quando**
- Ogni 20 s; 60 s a bot fermo.

**Numeri**
- 5 al minuto (fermo), 11 al minuto di media su 5 minuti.

**Esempio con le cifre**
- In 5 minuti: 28 letture delle operazioni, 4 delle missioni, 4 delle richieste manuali.

**Cosa vedi nell'app**
- Pagina Omega.

**Se qualcosa va storto**
- Tempo massimo di attesa 20 s per lettura.

**Per il tecnico**
- D-14 `Betfair/omega/omega_service.py:7809`, `Betfair/omega/omega_service.py:7496`.

## Coda ordini e regole

**Cosa fa**
- Contiene gli ordini in attesa (strada della coda), le regole di rischio (stop, bracket) e le
  impostazioni degli ordini (prova o vero, freno).

**Quando**
- Letta dal runner circa ogni secondo.

**Numeri**
- 189 + 168 + 123 = 480 letture al minuto.

**Esempio con le cifre**
- Lo schermo mette un ordine in coda alle 18:00:00.0: il runner lo prende entro le 18:00:01.

**Cosa vedi nell'app**
- Gli ordini «in attesa».

**Se qualcosa va storto**
- Una richiesta rimasta a meta' viene chiusa alla ripartenza del runner.

**Per il tecnico**
- Tabelle `betfair_live_order_requests`, `betfair_live_risk_rules`; funzione `get_live_settings`.

## Partite seguite e conto

**Cosa fa**
- Lista delle partite da seguire, ordini, regolati, battito del runner, saldo.

**Quando**
- Partite seguite ogni 2 s; battito ogni 10 s; saldo quando cambia.

**Numeri**
- 62 al minuto (29 partite seguite, 11 ordini, 11 regolati, 8 battiti, 2 saldi, 1 lista
  personale).

**Esempio con le cifre**
- 8 battiti in 60 s: uno ogni 7,5 s circa (battito ogni 10 s piu' quello del guardiano ogni 30 s).

**Cosa vedi nell'app**
- Testata (battito) e saldo.

**Se qualcosa va storto**
- Battito vecchio = l'app segnala il runner come fermo.

**Per il tecnico**
- D-6 `Betfair/stream/runner.py:1539`, `Betfair/stream/runner.py:1001`; tabelle `live_follow`,
  `betfair_live_orders`, `betfair_live_settled`, `betfair_live_heartbeat`, `betfair_live_account`.

## Tabelle di Mike

**Cosa fa**
- Operazioni, comandi, richieste, eventi delle partite, attivita' di Mike.

**Quando**
- A ogni giro di Mike.

**Numeri**
- 265 al minuto.

**Esempio con le cifre**
- Pulsante «ferma Mike»: la richiesta finisce qui, Mike la legge entro 1 s.

**Cosa vedi nell'app**
- Pagina di Mike.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `mike_trades`, `mike_control`, `mike_requests`, `mike_events`, `mike_activity`; funzione
  `get_mike_aggregates`.

## Tabelle di Safe

**Cosa fa**
- Operazioni, richieste, comandi, opportunita', attivita' di Safe.

**Quando**
- A ogni giro di Safe.

**Numeri**
- 259 al minuto.

**Esempio con le cifre**
- 19 riletture al minuto dei riassunti (aggregati) per la testata.

**Cosa vedi nell'app**
- Pagina Safe.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `safe_strategy_trades`, `safe_strategy_requests`, `safe_strategy_control`,
  `safe_strategy_opportunities`; funzione `get_safe_aggregates`.

## Tabelle di Omega

**Cosa fa**
- Operazioni, comandi, richieste manuali, missioni di Omega.

**Quando**
- A ogni giro di Omega.

**Numeri**
- 5 al minuto (fermo).

**Esempio con le cifre**
- 4 letture delle operazioni e 1 dei comandi nel minuto misurato.

**Cosa vedi nell'app**
- Pagina Omega.

**Se qualcosa va storto**
- -

**Per il tecnico**
- `omega_trades`, `omega_control`, `omega_manual_requests`, `omega_missions`.

## Frecce

- Runner calcio -> coda ordini e regole: 480 al minuto.
- Runner calcio -> partite seguite e conto: 62 al minuto.
- Runner calcio -> righe dello scanner: legge 10 al minuto.
- Scanner -> righe dello scanner: scrive 74 al minuto (righe 68, stato 5, una lettura).
- Mike -> righe dello scanner: legge 14 al minuto.
- Safe -> righe dello scanner: legge 10 al minuto.
- Mike -> tabelle di Mike: 265 al minuto.
- Safe -> tabelle di Safe: 259 al minuto.
- Omega -> tabelle di Omega: 5 al minuto.
- Non disegnata (troppo piccola): scanner -> posizioni dei bot, 12 al minuto (capitolo 6).

## Punti da decidere

1. Il runner calcio rilegge coda, regole e impostazioni circa 8 volte al secondo in tutto, anche
   quando la coda e' vuota.
2. Safe legge i comandi due volte per giro; Mike rilegge le operazioni circa 2 volte al secondo.

## Punti non chiariti

1. Il minuto misurato e' uno solo. Con piu' partite seguite e ordini in corso le scritture
   (partite, ordini, posizioni) crescono.
