## 10. Cosa ho verificato di persona / cosa non ho potuto verificare

### 10.1 Verificato

1. **Righe**: confronto indipendente con `wc -l` su 6 voci (sezione 0): tutte identiche a `s01`. HEAD e stato dell'albero (due file modificati da un'altra sessione) dichiarati in testa.
2. **Falsificazione degli script del primo giro** (difetti trovati e corretti, con effetto sui numeri): `s01` contava un PDF e i `.pkl` come testo (168.866 «righe» false nel blocco «altro»); `s02` non risolveva
   `ai_engine.*` (5 moduli di `Ai Engine/` erano falsi «morti», gruppo A 31 -> 26); `k02` aveva 16 falsi `SyntaxError` (BOM); `k03` (nuovo) all'inizio dava `parse.py` «avviato da `main.js`» per la parola `parse` e `test.py` «lanciato dal workflow» per
   `test_seasons`: corretto richiedendo il nome file con estensione; `s08` segnala ancora falsi positivi per stem generici (`pipeline`, `backfill`, ...), dichiarati in 2.5; `s03` dichiarava «33 tabelle mai usate» ma 12 sono toccate per stringa (`s05`).
3. **Controprove incrociate**: `s02` (AST) contro `s08` (stringa) per i morti; `f01` contro `strumenti/dati_J/accessi.tsv` (160 vs 159+2 RPC); `s03` contro `s05` per le tabelle «mai usate»;
   le citazioni dell'inventario del 02/10 contro il codice di oggi (`c01`); i numeri del brief contro `s01` e contro la ricostruzione (la somma delle sue componenti).
4. **Citazioni controllate a mano contro il codice** (letto il file alla riga): `desktop/main.js:413-484` (tutti i `spawnRunner`), `:46`, `:61`, `:292`, `:527-575`, `:759`, `:899`; `desktop/preload.js:21`; `watchdog.py:73-105,248-252,307,318`;
   `single_instance.py:18-35`; `local_channel.py:14-18,65,68,404`; `db_client.py:75`; `Betfair/mike/service.py:6794-6845`; `canale_bot.py:60-166`; `scalper_service.py:702-713`; `tennis_bot_service.py:1104,1136-1160`; `backtest/worker.py:23`;
   `frontend/src/lib/localChannel.ts:50-67,302-345`; `frontend/src/lib/uiShell.ts`; `App.tsx` (due alberi); `MISURE_2026-10-02.md` per ogni numero e riga citati (letto per intero, 253 righe).
5. **Nessuna esecuzione di codice di produzione**, nessun accesso al DB, nessuna chiamata a Betfair; i soli processi lanciati sono i miei script e `git` (un `du` su directory enormi e' stato avviato e subito interrotto dopo il timeout, senza risultati).

### 10.2 NON verificato (e perche')

1. **Cosa gira davvero sul PC** (processi vivi, RAM, CPU, quante finestre/renderer di Electron): non ho interrogato il sistema operativo; la sezione 5 descrive cio' che il codice avvia.
2. **Stato degli interruttori `*_CANALE`** e di ogni variabile `.env` (non letto): il verso di default e' nel codice, il valore reale no (sezione 5.4).
3. **Cosa c'e' sul DB cloud**: se le 21 tabelle senza riferimenti sono ancora popolate da `pg_cron`/funzioni, se le Edge Functions di `Telegram bot/` sono deployate, lo schema delle 17 tabelle non definite nei `.sql`, i vincoli e gli indici. Servirebbero letture `SELECT` su `pg_stat_user_tables`/`cron.job`, fuori dal perimetro di questo compito.
4. **Frequenze nuove**: nessuna misura nuova (regola del compito). Tutte le frequenze citate sono quelle del 02/10, con condizioni dichiarate (Omega fermo, niente tennis/scalper); non descrivono il carico di oggi ne' di una giornata piena.
5. **Chiamate a Betfair**: non contate una per una (nessun contatore nei registri, come gia' il 02/10); le cadenze Betfair dell'inventario del 02/10 (B-4...B-16) non sono state rimisurate.
6. **Raggiungibilita' vera dei moduli**: i gruppi A-D e la classifica di radice usano i collegamenti nel repo, non la raggiungibilita' dai punti d'ingresso; un modulo importato solo da un modulo morto risulta vivo. Gli import dinamici sono registrati (502) ma non risolti uno per uno.
7. **Frontend**: la chiusura degli import e' un limite superiore (una pagina che importa un hub eredita tutte le sue RPC); le RPC realmente chiamate da ogni pagina vanno derivate da `f01_pagine.txt`/`f01_accessi_file.tsv` pagina per pagina; i pannelli (6.4) sono elencati per dimensione, non descritti; le funzionalita' complete sono materia di `01_FUNZIONALITA.md`. `getLocalChannel(sport)` con argomento variabile risulta «variabile».
8. **Matrice DB**: operazione (lettura/scrittura) dedotta dal metodo concatenato; i `.table(x)` con nome non letterale (6 nomi) sono in «op?»; le chiamate DB fatte con SQL grezzo dentro RPC non si vedono; le RPC chiamate solo da trigger/cron non compaiono.
9. **Natura di `_checkpoint_2026-09-28/`** (58.058 file non tracciati) e delle altre cartelle locali non tracciate (7.1 punto 10): elencate, non indagate.
10. **Albero di lavoro non committato** di un'altra sessione (`db_client.py`, `season_gaps.py`): i numeri di quei file e dei loro derivati possono cambiare al commit.
