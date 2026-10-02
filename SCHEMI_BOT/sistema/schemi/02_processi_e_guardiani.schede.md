# Sistema - Capitolo 2: i programmi accesi dall'app e i loro guardiani (schede)

Schema: `02_processi_e_guardiani.html` (sorgente `02_processi_e_guardiani.architecture.json`).
Fonte dei fatti: `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md`, sezione A.

Schede dell'inventario usate: A-1 ... A-22.

Come si legge: l'app accende 8 programmi, ciascuno dentro un suo guardiano (un piccolo programma
che lo sorveglia e lo riaccende se cade). Il job delle quote tennis parte da solo, senza guardiano,
ogni 30 minuti. Ogni programma ha una «porta di guardia» sul computer: se la porta e' gia' presa,
vuol dire che una copia e' gia' accesa e la seconda copia si spegne.

---

## App desktop

**Cosa fa**
- All'apertura accende i 9 programmi; alla chiusura li spegne tutti.

**Quando**
- All'apertura e alla chiusura dell'app.

**Numeri**
- 8 programmi sotto guardiano, piu' le quote tennis ogni 30 minuti.
- Alla chiusura aspetta ogni programma fino a: scalper 150 s, Omega e Safe 45 s, gli altri 25 s.

**Esempio con le cifre**
- Il 02/10 alle 16:25 l'app si e' aperta e tutti i registri dei programmi cominciano alle 16:25:19.

**Cosa vedi nell'app**
- Niente di diretto; i registri finiscono nella cartella `_logs`.

**Se qualcosa va storto**
- Alla chiusura scrive il file ARRESTO: ogni programma chiude da solo. Chi non esce entro il suo
  tempo viene spento a forza insieme ai suoi figli: nessun programma resta acceso da solo.

**Per il tecnico**
- A-1 `desktop/main.js:351`; A-18 `desktop/main.js:535`, `desktop/main.js:497`.

## Guardiani

**Cosa fa**
- Ognuno sorveglia un programma: se cade lo riaccende, se esce pulito lo lascia spento.

**Quando**
- Per tutta la vita del programma sorvegliato.

**Numeri**
- Riaccensione dopo 10 s, poi 20, 40, 80, 160, fino a 300 s.
- Al massimo 5 riaccensioni in un'ora.
- Uscita entro 5 secondi dall'avvio = copia gia' accesa: il guardiano si ferma.

**Esempio con le cifre**
- Mike cade alle 18:00:00: avviso grave e Telegram, Mike riparte alle 18:00:10. Se cade 6 volte
  in un'ora, alla sesta il guardiano si ferma e scrive «SERVE INTERVENTO MANUALE».

**Cosa vedi nell'app**
- Gli avvisi nella striscia degli avvisi.

**Se qualcosa va storto**
- Il guardiano non muore se il database o Telegram sono giu': salta l'avviso e continua.
- Un ricambio pianificato del runner (codice 75) lo riaccende subito, senza avviso grave.

**Per il tecnico**
- A-11 ... A-15 `Betfair/stream/watchdog.py:73-109`, `Betfair/stream/watchdog.py:289-328`.

## Avvisi nel database

**Cosa fa**
- Raccoglie gli avvisi dei guardiani (e di altri programmi) nella tabella degli avvisi; i
  guardiani mandano anche un messaggio Telegram.

**Quando**
- A ogni caduta, uscita pulita o copia doppia.

**Numeri**
- Tre livelli: informazione, attenzione, grave.

**Esempio con le cifre**
- «RUNNER CRASHATO [Betfair.mike.service]: exit code 1 ... Riavvio n. 1 tra 10s.»

**Cosa vedi nell'app**
- La striscia degli avvisi.

**Se qualcosa va storto**
- Se il database non risponde l'avviso si perde, il guardiano continua.

**Per il tecnico**
- A-16 `Betfair/stream/watchdog.py:144`; tabella `live_alerts`.

## Quote tennis

**Cosa fa**
- Scarica le partite di tennis del giorno con le quote e le scrive nella lista «Partite del giorno».

**Quando**
- All'apertura dell'app e poi ogni 30 minuti; finito il lavoro esce.

**Numeri**
- Il 02/10: 2 giri (16:25 e 16:55), 27 partite scritte al secondo giro.

**Esempio con le cifre**
- Alle 16:55 ha scritto 27 partite e si e' chiuso.

**Cosa vedi nell'app**
- La lista delle partite tennis del giorno.

**Se qualcosa va storto**
- Non ha guardiano. Se il giro precedente e' ancora vivo, il nuovo giro viene saltato.

**Per il tecnico**
- A-10 `desktop/main.js:484-491`; porta di guardia 47316 `betfair_tennis_odds.py:304`.

## Runner calcio

**Cosa fa**
- Tiene la linea con Betfair per il calcio e piazza gli ordini calcio.

**Quando**
- Sempre; senza partite aspetta e ricontrolla ogni 2 secondi.

**Numeri**
- Porta di guardia 47311. E' l'unico per cui il guardiano scrive un battito (ogni 30 s).

**Esempio con le cifre**
- Se cade alle 18:00, alle 18:00:10 riparte e riapre la linea con Betfair.

**Cosa vedi nell'app**
- Il battito del runner nella testata.

**Se qualcosa va storto**
- Mentre e' giu' non si piazzano ordini calcio in prova; quelli veri di Mike vanno lo stesso
  (Mike va diretto, capitolo 7).

**Per il tecnico**
- A-2, A-17, A-19 `Betfair/stream/runner.py:1203`.

## Runner tennis

**Cosa fa**
- Tiene la linea per il tennis e ospita i 4 bot tennis.

**Quando**
- Sempre.

**Numeri**
- Porta di guardia 47312.

**Esempio con le cifre**
- Il 02/10 dalle 16:25 alle 17:16 ha scritto 1.474 volte «nessun evento: attendo».

**Cosa vedi nell'app**
- Le pagine del tennis.

**Se qualcosa va storto**
- Riacceso dal guardiano; i bot tennis ripartono con lui.

**Per il tecnico**
- A-3, A-19 `Betfair/stream/tennis_live/tennis_runner.py:1975`.

## Scanner

**Cosa fa**
- Raccoglie quote e punteggi per tutti i bot (capitolo 6).

**Quando**
- Sempre.

**Numeri**
- Porta di guardia 47315.

**Esempio con le cifre**
- Alle 17:16 seguiva 40 partite.

**Cosa vedi nell'app**
- Quote e punteggi in tutte le pagine dei bot.

**Se qualcosa va storto**
- Riacceso dal guardiano; nel frattempo i bot non ricevono quote nuove.

**Per il tecnico**
- A-6, A-19 `Betfair/safe_strategy/service.py:74`.

## Mike

**Cosa fa**
- Bot Under 3,5 e Over 4,5.

**Quando**
- Sempre acceso come programma; opera solo se l'utente lo accende dalla pagina.

**Numeri**
- Porta di guardia 47319.

**Esempio con le cifre**
- Riacceso dopo una caduta con la stessa impronta di avvio dell'app: se era acceso resta acceso.

**Cosa vedi nell'app**
- La pagina di Mike.

**Se qualcosa va storto**
- Se l'app viene riaperta (impronta nuova), nessun bot opera finche' l'utente non lo riaccende.

**Per il tecnico**
- A-9, A-19 `Betfair/mike/config.py:32`; impronta `APP_BOOT_ID` `desktop/main.js:357`.

## Bot Safe

**Cosa fa**
- Esegue i segnali Safe.

**Quando**
- Sempre acceso come programma; opera solo se acceso dall'utente.

**Numeri**
- Porta di guardia 47318. Alla chiusura dell'app ha 45 s per chiudere da solo.

**Esempio con le cifre**
- Chiudi l'app alle 20:00:00: Safe ha tempo fino alle 20:00:45, poi viene spento a forza.

**Cosa vedi nell'app**
- La pagina Safe Strategy.

**Se qualcosa va storto**
- Riacceso dal guardiano.

**Per il tecnico**
- A-8, A-19 `Betfair/safe_strategy/bot_service.py:139`.

## Omega

**Cosa fa**
- Bot che banca il risultato esatto.

**Quando**
- Sempre acceso come programma; opera solo se acceso dall'utente.

**Numeri**
- Porta di guardia 47313. Alla chiusura 45 s per chiudere da solo.

**Esempio con le cifre**
- Il 02/10 all'avvio il registro dice: «il bot era gia' fermo in prova».

**Cosa vedi nell'app**
- La pagina Omega.

**Se qualcosa va storto**
- Riacceso dal guardiano.

**Per il tecnico**
- A-7, A-19 `Betfair/omega/omega_service.py:8293`.

## Scalper calcio

**Cosa fa**
- Capo delle sessioni scalper: una sessione (programma figlio) per partita.

**Quando**
- Sempre; gira ogni 3 secondi.

**Numeri**
- Porta di guardia 47314. Alla chiusura ha 150 s per chiudere le sessioni.

**Esempio con le cifre**
- 3 partite armate = 3 sessioni accese, ognuna con la sua linea Betfair.

**Cosa vedi nell'app**
- Il pannello scalper.

**Se qualcosa va storto**
- Una sessione che cade o si ferma annulla i suoi ordini aperti su Betfair.

**Per il tecnico**
- A-4, A-22 `Betfair/stream/scalper/scalper_service.py:663`; B-8.

## Ponte tennis

**Cosa fa**
- Mette in lista le partite dei bot tennis armati. Non tocca Betfair.

**Quando**
- Ogni 15 secondi, o subito con la sveglia.

**Numeri**
- Nessuna porta di guardia in questo modo (la tiene il runner tennis).

**Esempio con le cifre**
- Armi il bot tennis su una partita: entro 15 s la partita entra nella lista del runner tennis.

**Cosa vedi nell'app**
- Lo stato dei bot tennis.

**Se qualcosa va storto**
- Riacceso dal guardiano.

**Per il tecnico**
- A-5, A-21 `Betfair/stream/tennis_live/tennis_bot_service.py:1128`.

## Frecce

- App -> Guardiani: all'apertura accende 8 programmi, ognuno col suo guardiano.
- App -> Quote tennis: ogni 30 minuti, senza guardiano.
- Guardiani -> Avvisi: a ogni caduta (grave + Telegram), uscita pulita (informazione), copia
  doppia (attenzione).
- Guardiani -> ciascuno degli 8 programmi: sorveglia e riaccende (freccia senza scritta: e' sempre
  la stessa cosa).

## Punti da decidere

1. Il job delle quote tennis non ha guardiano: se fallisce un giro, la lista resta quella di 30
   minuti prima.

## Punti non chiariti

1. Nei registri del 02/10 dalle 16:25 alle 17:16 nessun guardiano ha registrato cadute o
   riaccensioni (nessuna riga «figlio uscito» o «RUNNER CRASHATO»). Le giornate precedenti non sono
   state lette.
