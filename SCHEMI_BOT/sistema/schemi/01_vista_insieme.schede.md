# Sistema - Capitolo 1: chi parla con chi (schede)

Schema: `01_vista_insieme.html` (sorgente `01_vista_insieme.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md` e `SCHEMI_BOT/sistema/MISURE_2026-10-02.md`.

Schede dell'inventario usate: A-1 ... A-10, B-4, B-7, B-8, B-9, D-M, G-1, G-3, G-4.

Come si legge: a sinistra Betfair e i quattro programmi che tengono una linea continua con
Betfair; al centro il database; a destra i bot che lavorano soprattutto col database; sotto
l'app. Il numero su ogni freccia e' quante chiamate al database quel programma ha fatto in un
minuto, il 02/10/2026 dalle 17:15:40 alle 17:16:40 (ora italiana). Piu' spessa la freccia, piu'
chiamate.

---

## Betfair

**Cosa fa**
- E' la borsa delle scommesse (sito .it). Manda i prezzi e lo stato degli ordini.

**Quando**
- Sempre, finche' un programma tiene la linea aperta.

**Numeri**
- 4 programmi tengono una linea continua: runner calcio, scanner, runner tennis, sessioni scalper.

**Esempio con le cifre**
- Il 02/10 alle 17:16 lo scanner seguiva 40 partite con le sue linee continue.

**Cosa vedi nell'app**
- Le quote che si muovono nelle schermate arrivano da qui, passando dai programmi.

**Se qualcosa va storto**
- Se una linea cade, il programma la riapre; lo scanner nel frattempo chiede le quote una per una
  (capitolo 6).

**Per il tecnico**
- B-4 `Betfair/stream/runner.py:2805`; B-9 `Betfair/safe_strategy/stream.py:81`; B-7
  `Betfair/stream/tennis_live/tennis_runner.py:469`; B-8 `Betfair/stream/scalper/scalper_session.py:1187`.

## Runner calcio

**Cosa fa**
- Tiene la linea con Betfair per le partite di calcio seguite e piazza gli ordini calcio di tutti
  (bot e ordini a mano).

**Quando**
- Sempre acceso finche' l'app e' aperta.

**Numeri**
- 552 chiamate al minuto al database: e' il programma che ne fa di piu'.

**Esempio con le cifre**
- In un minuto: 189 letture della coda ordini, 168 letture delle regole di rischio, 123 letture
  delle impostazioni degli ordini.

**Cosa vedi nell'app**
- Le quote del calcio e gli ordini nella pagina di trading.

**Se qualcosa va storto**
- Se cade, il suo guardiano lo riaccende (capitolo 2). Senza runner gli ordini in prova (paper)
  dei bot vengono rifiutati.

**Per il tecnico**
- A-2 `desktop/main.js:435`, `Betfair/stream/watchdog.py:65`; misure D-M.

## Scanner

**Cosa fa**
- Raccoglie quote e punteggi di tutte le partite interessanti e li passa a tutti i bot.

**Quando**
- Sempre acceso; gira ogni 0,5 secondi.

**Numeri**
- 86 chiamate al minuto al database, quasi tutte scritture delle sue righe (68).

**Esempio con le cifre**
- Alle 17:16 pubblicava le righe di 40 partite seguite.

**Cosa vedi nell'app**
- La Control Room e le pagine dei bot mostrano le sue quote e i punteggi.

**Se qualcosa va storto**
- Se cade, tutti i bot restano senza quote nuove finche' il guardiano non lo riaccende.

**Per il tecnico**
- A-6 `desktop/main.js:459`; E-1 `Betfair/safe_strategy/service.py:431`.

## Runner tennis

**Cosa fa**
- Tiene la linea con Betfair per le partite di tennis seguite e ospita i 4 bot tennis.

**Quando**
- Sempre acceso; senza partite aspetta e ricontrolla la lista ogni 2 secondi.

**Numeri**
- 28 chiamate al minuto al database (tutte letture della lista delle partite da seguire).

**Esempio con le cifre**
- Il 02/10 alle 17:16 non c'era nessuna partita tennis seguita: 28 letture al minuto a vuoto.

**Cosa vedi nell'app**
- Le quote del tennis e gli ordini dei bot tennis.

**Se qualcosa va storto**
- Se cade, il guardiano lo riaccende.

**Per il tecnico**
- A-3 `desktop/main.js:436`; D-15 `Betfair/stream/tennis_live/tennis_runner.py:3012`.

## Scalper calcio

**Cosa fa**
- E' il capo delle sessioni scalper: accende una sessione (un programma a parte) per ogni partita
  armata.

**Quando**
- Sempre acceso; rilegge i comandi ogni 3 secondi.

**Numeri**
- 54 chiamate al minuto al database.

**Esempio con le cifre**
- In un minuto: 18 letture dei comandi delle sessioni, 18 dell'interruttore generale, 18 delle
  impostazioni (freno).

**Cosa vedi nell'app**
- Il pannello scalper e la riga scalper della Control Room.

**Se qualcosa va storto**
- Se cade, il guardiano lo riaccende.

**Per il tecnico**
- A-4 `desktop/main.js:443`; A-22 `Betfair/stream/scalper/scalper_service.py:663`.

## Database Supabase

**Cosa fa**
- Fa da postino: ogni programma vi lascia e vi riprende le notizie (ordini, comandi, posizioni,
  quote dello scanner).

**Quando**
- Sempre.

**Numeri**
- 1.309 chiamate al minuto in tutto, circa 22 al secondo.

**Esempio con le cifre**
- 552 (runner calcio) + 279 (Mike) + 269 (Safe) + 86 (scanner) + 54 (scalper) + 36 (ponte
  tennis) + 28 (runner tennis) + 5 (Omega) = 1.309.

**Cosa vedi nell'app**
- Quasi tutto quello che l'app mostra passa di qui (capitolo 8).

**Se qualcosa va storto**
- Se il database rallenta, i bot rallentano: i bot hanno un tempo massimo di attesa di 20 secondi
  per lettura.

**Per il tecnico**
- D-M; D-1 `db_client.py:60`.

## Mike

**Cosa fa**
- Bot Under 3,5 e Over 4,5 sul calcio. Legge le quote dallo scanner, non ha una linea propria.

**Quando**
- Gira ogni 1 secondo (5 secondi quando non ha niente da fare).

**Numeri**
- 279 chiamate al minuto al database.

**Esempio con le cifre**
- In un minuto: 116 letture delle sue operazioni, 58 dei comandi, 58 delle richieste.

**Cosa vedi nell'app**
- La pagina di Mike.

**Se qualcosa va storto**
- Se cade, il guardiano lo riaccende.

**Per il tecnico**
- A-9 `desktop/main.js:477`; A-20 `Betfair/mike/service.py:7432`.

## Bot Safe

**Cosa fa**
- Esegue i segnali della strategia Safe (calcio e tennis).

**Quando**
- Gira ogni 2 secondi.

**Numeri**
- 269 chiamate al minuto al database.

**Esempio con le cifre**
- In un minuto: 81 letture delle operazioni, 97 tra letture e scritture delle richieste, 55 sui
  comandi.

**Cosa vedi nell'app**
- La pagina Safe Strategy.

**Se qualcosa va storto**
- Se cade, il guardiano lo riaccende.

**Per il tecnico**
- A-8 `desktop/main.js:472`; A-20 `Betfair/safe_strategy/bot_service.py:10677`.

## Omega

**Cosa fa**
- Bot che banca il risultato esatto.

**Quando**
- Gira ogni 20 secondi (60 secondi quando e' fermo).

**Numeri**
- 5 chiamate al minuto il 02/10 alle 17:16 (era fermo).

**Esempio con le cifre**
- In 5 minuti: 57 chiamate, cioe' 11 al minuto.

**Cosa vedi nell'app**
- La pagina Omega.

**Se qualcosa va storto**
- Se cade, il guardiano lo riaccende.

**Per il tecnico**
- A-7 `desktop/main.js:466`; A-20 `Betfair/omega/omega_service.py:8621`.

## Ponte tennis

**Cosa fa**
- Per ogni bot tennis armato si assicura che la partita sia nella lista da seguire.

**Quando**
- Ogni 15 secondi. Non parla con Betfair.

**Numeri**
- 36 chiamate al minuto al database.

**Esempio con le cifre**
- In un minuto: 18 letture dei comandi dei bot tennis, 12 battiti scritti (uno per bot).

**Cosa vedi nell'app**
- Lo stato dei 4 bot tennis.

**Se qualcosa va storto**
- Se cade, il guardiano lo riaccende.

**Per il tecnico**
- A-5 `desktop/main.js:453`; A-21 `Betfair/stream/tennis_live/tennis_bot_service.py:1128`.

## App desktop

**Cosa fa**
- Accende tutti i programmi, mostra le schermate e manda i comandi dei pulsanti.

**Quando**
- Dall'apertura alla chiusura.

**Numeri**
- Le schermate rileggono lo stato ogni 15 secondi (Mike, Safe, Omega) e ogni 30 secondi
  (Control Room), piu' gli aggiornamenti istantanei.

**Esempio con le cifre**
- Premi «accendi Mike»: il comando va nel database; Mike lo vede al giro dopo (entro 1 secondo)
  o subito con la sveglia.

**Cosa vedi nell'app**
- E' l'app stessa.

**Se qualcosa va storto**
- Se l'app si chiude, chiude tutti i programmi (capitolo 2).

**Per il tecnico**
- G-1 `desktop/main.js:25`; G-3 `frontend/src/lib/mike.ts:2228`; G-5.

## Frecce

- Betfair -> runner calcio, scanner, runner tennis, scalper: linea continua (prezzi in diretta;
  per i runner anche gli ordini). La freccia non ha scritta perche' e' sempre la stessa cosa,
  scritta dentro il riquadro di Betfair.
- Runner calcio -> database: 552 chiamate al minuto.
- Scanner -> database: 86 al minuto.
- Runner tennis -> database: 28 al minuto.
- Scalper -> database: 54 al minuto.
- Mike -> database: 279 al minuto.
- Safe -> database: 269 al minuto.
- Omega -> database: 5 al minuto (fermo).
- Ponte tennis -> database: 36 al minuto.
- App -> database: legge lo stato e scrive i comandi.

## Punti da decidere

1. Il database fa da postino per tutto: 1.309 chiamate al minuto. Tre
   programmi (runner calcio, Mike, Safe) fanno l'84% del traffico. Da decidere se e quando
   spostare queste riletture sui fili diretti.

## Punti non chiariti

1. I numeri sono di UN minuto con Omega fermo, nessuna partita tennis e nessuna sessione scalper:
   con tutti i bot accesi i numeri saranno piu' alti.
