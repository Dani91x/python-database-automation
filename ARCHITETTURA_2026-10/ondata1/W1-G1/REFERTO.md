# REFERTO W1-G1 - Comparto G: archivio locale invisibile e postino (ondata 1, 09/10/2026)

Ramo `architettura/w1-g1` da `559a96df`. Nessun file esistente modificato: solo file NUOVI del dominio W1-G1.
Doc del comparto: `Betfair/nucleo/dati/doc/G1_ARCHIVIO_POSTINO.md`. In questa cartella: `misura_g1.py` + `misure_g1.txt`,
`mutazioni_g1.py` + `mutazioni_g1.txt`.

## 1. Cosa ho costruito (e cosa NON fa)

| File (righe) | Punti chiave |
|---|---|
| `Betfair/nucleo/dati/percorso.py` (173) | `cartella_base` :64 (`ARCH_ARCHIVIO_DIR` > `%LOCALAPPDATA%\AlphaScore Trading\archivio` > XDG), MAI nel repo (`PercorsoNonAmmesso`, controlli :81 e :91); `cartella_processo` :86 (una cartella per processo, nome validato); `Lucchetto` :110 (msvcrt/fcntl, il SO lo rilascia anche con `os._exit`). Nessuna configurazione dell'utente |
| `Betfair/nucleo/dati/schema_locale.py` (216) | schema GENERICO v1 :43-105 (`righe`, `outbox`, `dead_letter`, `consegna`, `riconciliazioni`, `segnalazioni`): non nomina NESSUNA tabella del cloud; `applica_schema` :118 (`PRAGMA user_version`, una transazione per migrazione, `auto_vacuum=INCREMENTAL`, rifiuto di uno schema piu' nuovo); `chiave_canonica` :144 (= `jsonb_build_array(...)::text`); `rev_ordinabile` :159; riga JSONL :191 |
| `Betfair/nucleo/dati/archivio.py` (964) | `ArchivioLocale` :166 (implementa `Archivio`); `apri` :216 (lucchetto, schema, riparazione dei log troncati :647, due thread); `scrivi` :310; `leggi` :333 (vede anche cio' che e' in coda); `transizione` :349 (claim nel thread di scrittura); `accoda` :379 (forma sincrona con seq); `conferma` :398 (barriera di durabilita', R03); thread di scrittura :454 (riga + outbox nella STESSA transazione :572-612, group commit, ritento senza scarto :477, riavvolgimento dei log su lotto fallito :635); API per postino e riconcilia :693-845; manutenzione :856 (checkpoint PASSIVE fuori dal commit :878, pulizia :888 solo di cio' che e' consegnato E riconciliato, mai dead_letter) |
| `Betfair/nucleo/dati/postino.py` (606) | `PostinoLocale` :156 (implementa `Postino`); `drena` :219: raccolta a quota equa :290, gruppi = corse (tabella, op) nell'ordine di arrivo, padri prima :374, consegna :403, esito per riga :432, errore della chiamata :453 (rete -> offline, attese 2-4-8-16-32-60 s; 57014 -> blocco dimezzato :470; altro -> tabella bloccata, mai dead_letter); `stato` :197; ombra :189; tetto di disco :548; `riconcilia` :246; `avvia` :256 (thread che drena e riconcilia di notte :564, giorno :581) |
| `Betfair/nucleo/dati/riconcilia.py` (169) | `Riconciliatore.confronta` :83 (mancanti esclusa la coda, in piu', versioni diverse); `confronta_ombra` :156 (criterio di T8) |
| `migrations/architettura_uid_ombra_2026-10-09.sql` (460) | `uid uuid` + indice unico sulle 10 tabelle di log, `trade_uid` sulle 3 dei trade :44; `_postino_crea_ombra` :86 (LIKE INCLUDING ALL, niente FK, sequenze proprie, RLS) + 21 ombre :175; RPC `postino_consegna` :200, `postino_impronte` :344, `postino_confronta_ombra` :408; permessi solo `service_role` |

**Cosa NON fa**: non si aggancia a nessun codice di oggi (ondata 2); nessuna rete propria (il cloud e' iniettato:
protocollo `Cloud`, client unico di W1-G2); nessun thread ne' file all'import (provato da `test_import_non_apre_file_ne_thread`);
nessuna decisione sulle righe (soglie, stati dei bot); non toglie l'`insert_trade` sincrono (U-80, R01): per i trade solo
`trade_uid` e ombre. La migrazione NON e' applicata: la applica l'utente.

## 2. Contratto

Implementati: `Archivio` (`ArchivioLocale`) e `Postino` (`PostinoLocale`), firme verificate parametro per parametro
(`conforme()` nei test); `Cloud` usato come protocollo (nei test: `CloudProva` sul client supabase VERO). Tipi del
contratto restituiti tali e quali. Contratto non toccato.

**Estensioni proposte** (oggi argomenti/metodi in piu' nei miei file):
1. `SpecTabella.colonna_tempo` (oggi `COLONNE_TEMPO_PREDEFINITE` in `archivio.py`): la colonna che il cloud riempie con
   `now()`; l'archivio la timbra all'accodamento e `riconcilia` ci fa la finestra (senza: «in piu' nel cloud» non calcolabile, con warning).
2. `SpecTabella.colonna_stato` (oggi `colonna_stato="status"`): la colonna del claim di `transizione`.
3. `Archivio.conferma(timeout_s) -> bool`: barriera per «prima la riga, poi l'invio» (R03, T14).
4. `Postino.avvia/ferma`, `riconcilia_giorno`, `riconciliazione_notturna`, attributo `ripiego_diretto`.
5. Eventi oltre ai tre del contratto: `dati.postino_online`, `dati.postino_bloccato`, `dati.tetto_disco` (+`_rientrato`),
   `dati.riga_troncata`, `dati.archivio_guasto`/`_ripreso`.

## 3. Parita'

| Oggi (file:riga) | Nuovo | Test | Esito |
|---|---|---|---|
| riga inserita da `mike/db.py:71` `log`, `omega/omega_db.py:61` `log`, `safe_strategy/bot_db.py:87` `log`, `stream/db.py:690` `insert_alert` (troncamento a 500), `stream/db.py:981` `insert_live_journal` | `ArchivioLocale.scrivi` + `PostinoLocale.drena` | `test_g1_parita.py` (5 casi: funzioni VERE chiamate davvero, corpo catturato dal client vero su MockTransport) | riga consegnata IDENTICA (stessa tabella, stesse chiavi, stessi valori); in piu' SOLO `uid` e la colonna del tempo, dichiarate |
| `db_client.classifica_guasto_rete` (`db_client.py:244`) e `ATTESE_RETE_S` (`:153`) | RIUSATI con import pigro (`postino.py:92,102`), nessuna copia | `test_guasti_di_rete_veri_*` (ConnectError, GOAWAY, 520 HTML), `test_cloud_fermo_*` (attese 2,4,8,16,32,60,60) | identico |
| riduzione del blocco su 57014 (`stream/db.py:26-37,579-628`) | stessa idea sul blocco della RPC (`postino.py:470`); NON sostituisce `insert_rows_resilient` (curatore, resta) | `test_57014_dimezza_il_blocco` | analogo, dichiarato |
| upsert per chiave naturale di oggi (G par. 1.1) | `postino_consegna` (SQL generico) | `test_g1_pg_reale.py` sul PostgreSQL vero | stesse chiavi; in piu' la versione monotona (R02) |
| log di oggi: insert semplice, errore -> warning e riga persa (`mike/db.py:79-80`) | insert `ON CONFLICT (uid) DO NOTHING`; errore -> dead_letter visibile | `test_check_rifiutato_*`, `test_ritento_dopo_risposta_persa_*` | MIGLIORE, dichiarato: 0 righe perse in silenzio, 0 doppioni al ritento |

Ingressi veri: colonne, CHECK e FK dalle migrazioni del repo (`mike_bot.sql:124-130`, `live_alerts.sql:22-30`,
`betfair_live_order_queue.sql:116`, `betfair_live_pnl_journal.sql:89`), anche sul PostgreSQL vero con le migrazioni di
base applicate. Le registrazioni del banco non servono a questo comparto (nessun dato di mercato).

## 4. Misure (`misura_g1.py <tmp> 3000 3`, uscita in `misure_g1.txt`)

Container cloud condiviso con gli altri agenti, NON il PC: sul PC si rilancia lo stesso comando. Microsecondi.

| Cosa | Esito (3 ripetizioni) | Confronto |
|---|---|---|
| ACCODAMENTO pagato dal chiamante (`scrivi`): denaro / vivo / log | p50 12,4-13,5 / 11,2-11,4 / 18,4-18,5; p99 66-77 / 43-62 / 166-1.424 | 04 par. 6.1 «~15 us»: rispettato al p50; il p99 dei log e' piu' alto (uid + timbro + JSON nel chiamante) |
| commit del denaro (FULL, lotti fino a 100) | p50 1,6-5,9 ms; max 31-53 ms | m06 FULL 1 commit/record (PC NVMe): 0,6 ms p50, max 67-180 ms |
| commit del vivo (NORMAL, lotti) | p50 0,19-0,32 ms; max 5,8-22,8 ms | m06 NORMAL lotti 0,78-0,93 ms p50 |
| flush dei log (per lotto) | p50 3,3-3,7 us; max 16-141 us | m06 write+flush 11 us per record |
| durevole-dopo (accodamento -> commit) su raffica di 3.000 | denaro p50 159-179 ms; vivo 66-144 ms; log 2,7-7,7 ms | raffica artificiale (3.000 in ~0,15 s); il carico vero e' ordini di grandezza sotto (101 richieste d'ordine in tutta la storia, 07 par. 7) |
| checkpoint nel thread di manutenzione (PASSIVE) | p50 14-19 ms, max 20-71 ms, FUORI dal commit | checkpoint nel commit (default): max del commit del vivo 25,8-39,0 ms contro 5,8-22,8 ms |
| U-55 un file contro due (commit del denaro FULL con il vivo a lotti, stesso thread) | UN file p99 8,2-15,9 ms, max 12-101 ms; DUE file p99 11,3-18,5 ms, max 16-30 ms | nel container nessuna differenza netta al p99; il massimo peggiore (101 ms) e' sul file unico. Da rimisurare sul PC |
| R08 (laboratorio): giro di decisione CPU con scrittore + postino accesi | 60 righe/s: p99 257-342 contro spento 229-280 (2 ripetizioni su 3 nella variabilita'); 600 righe/s: p99 314-603 e cadenza 228-249 giri/s contro 383-406 | il GIL si sente a carico alto. La prova vera (replay a cadenza reale, L2/L6) e' T8 sul PC; se peggiora, U-82 |
| crash del processo (`os._exit` a 0,25 / 0,6 / 1,0 s) | confermate 700 / 1.500 / 4.200; ritrovate 767 / 1.518 / 4.267; **confermate perse 0** | 07 par. 6.1: 0 persi con flush e con SQLite |

## 5. Test e falsificazioni

- Test nuovi: `test_g1_finti.py` 2, `test_g1_archivio.py` 17, `test_g1_postino.py` 27, `test_g1_crash.py` 4,
  `test_g1_parita.py` 5, `test_g1_pg_reale.py` 5 (solo con `G1_PG_PSQL`): **60 verdi** col PostgreSQL usa-e-getta;
  **55 verdi + 5 saltati** senza.
- Falsificazione (`mutazioni_g1.py --sql`, uscita `mutazioni_g1.txt`): **33/33 ROSSE** (30 sul Python + 3 sulla migrazione
  applicata al PostgreSQL usa-e-getta); ogni file ripristinato con sha256 identico. Coprono le cinque di G par. 5 (flush
  tolto; uid generato alla consegna -> il ritento duplica; cloud fermo non riconosciuto; CHECK ritentato invece di
  dead_letter) piu' 23503 definitivo (R06), figlio prima del padre, ombra sulle tabelle vere (R21), upsert senza versione
  (R02, SQL), esito non per riga (SQL), insert senza `ON CONFLICT` (SQL), offline che fa avanzare i log, riga alterata
  nel trasporto, fonte che affama le altre, riga piu' lunga del blocco, riconciliazione del giorno sbagliato.
- **Due difetti trovati e corretti prima della consegna (non nascosti)**:
  1. la misura ha scoperto che il thread `avvia` leggeva `esito.morte` (campo inesistente: e' `dead_letter`): ogni giro
     falliva, il test del thread passava lo stesso; test rinforzato (`ultimo_errore is None`), M19 lo riproduce, rosso;
  2. la mutazione M01 (flush tolto) e' SOPRAVVISSUTA a un secondo giro: il test di crash con morte a tempo la vede solo
     se la morte cade con righe nel buffer (12 perse in un caso, 0 in un altro). Aggiunta la prova DETERMINISTICA
     (raffica, `conferma()`, `os._exit` subito): M01 rossa 8 volte su 8, motivo «confermate e perse: [1459, 1462, ...]».
- Migrazione su PostgreSQL 16 usa-e-getta nel container (porta 54329; ruoli finti anon/authenticated/service_role BYPASSRLS
  e privilegi di default come Supabase; migrazioni di base del repo applicate): applicata DUE volte senza errori
  (idempotente); 21 ombre con sequenze proprie e senza FK; RLS attiva; `anon` -> «permission denied for function»;
  insert idempotente, CHECK 23514 e FK 23503 per riga, upsert con versione (la vecchia torna `ignorata`), impronte con
  `timestamptz` confrontate esattamente con l'ISO locale. Server fermato e cartella cancellata a fine lavoro.

### 5-bis. Suite intera (`python -m pytest Betfair/ -q -p no:cacheprovider`, due volte)

| Giro | Codice | Esito |
|---|---|---|
| 1 (a meta') | `d01b9d98` + test di parita' | **11.622 passed, 92 skipped, 6 xfailed, 0 failed** in 706 s |
| 2 (alla fine) | cima del ramo (*) | **11.626 passed, 92 skipped, 6 xfailed, 0 failed** in 370 s (+4 = i test nuovi del giro) |

(*) Durante il giro 2 ho sostituito nei COMMENTI le virgolette `«»` con `"` (codice ASCII-only): nessun cambio di
comportamento; dopo, i 60 test G1 (col PostgreSQL usa-e-getta ricreato) e le 33 mutazioni sono stati rilanciati sui file
definitivi: 60 verdi, 33/33 rosse (`mutazioni_g1.txt`, sha256 dei file finali: archivio `bec08ea9...`, postino
`46b6c67b...`, migrazione `24db8200...`). PostgreSQL di nuovo fermato e cancellato.
I 92 saltati comprendono i 5 di `test_g1_pg_reale.py` (senza `G1_PG_PSQL`). Un primo lancio del giro 1 e' stato fermato
da me dopo pochi secondi per un nome di file in conflitto (par. 9 punto 12): non conta come giro.

## 6. Funzionalita' di `01_FUNZIONALITA.md`

Coperte dal comparto (pronte, NON agganciate): G-013 (log, riduzione su 57014), G-014 (`insert_alert`, FK su
`live_follow`), G-016/G-017/G-018 (regimi e versione per specchio, posizioni, battito coalescente), G-019 (`log()` dei bot
senza perdita silenziosa), G-021 (solo `trade_uid` e ombre), G-023 (claim), G-004/G-005 (riusate). Tabella con i test nel
doc G1 par. 5. Restano al vecchio codice TUTTE finche' l'ondata 2 non accende gli interruttori.

## 7. PSB par. 6/7

Sollecitate: 6.3 (riavvio con stato su disco: crash vero), 6.5 (colonne e CHECK veri, PostgreSQL vero), 6.6 (claim con 8
thread, scrittore unico), 6.7 (33 mutazioni), 6.8 (comandi e strumenti nel referto); 7 n.18 (scrittura fallita mai
warning: dead_letter + evento), n.19 (stato su disco), n.21 (`mode` nella chiave naturale: paper e live mai fusi), n.27
(client vero, colonne vere), n.28-30 (test falsificati; due rinforzati dopo difetti veri).
⊘ con causa: 6.1, 6.2, 6.4, 6.9 e 7 n.1-17, n.20, n.22-26, n.31-35: il comparto non tocca mercato, scanner, ordini,
strategia ne' banco (nessun bot agganciato in questa ondata).

## 8. Aggancio proposto per l'ondata 2

### 8.1 Percorso invisibile allineato all'app
`desktop/ambiente_runner.js:60-83` (`costruisciEnvRunner`, pura): aggiungere `ARCH_ARCHIVIO_DIR: archivioDir`, passato da
`desktop/main.js:365` come `path.join(process.env.LOCALAPPDATA || app.getPath('userData'), 'AlphaScore Trading', 'archivio')`.
`app.getPath('userData')` di Electron sta in `%APPDATA%` (Roaming): per il WAL propongo `%LOCALAPPDATA%` (disco locale, mai
sincronizzato). Senza la variabile il Python sceglie gia' la stessa cartella.

### 8.2 T8 - log (`ARCH_POSTINO_LOG=vecchio|ombra|nuovo`, di serie `vecchio`)
Una facciata unica (file nuovo `nucleo/dati/facciata.py`, ondata 2) `scrivi_log(tabella, riga, vecchio)`: `vecchio` ->
insert di oggi; `ombra` -> insert di oggi + `archivio.scrivi` con `PostinoLocale(ombra=True)` (solo `<tabella>_ombra`);
`nuovo` -> solo `archivio.scrivi` (con `ripiego_diretto` vero: insert di oggi con lo STESSO `uid`). Punti (righe a `559a96df`):

| Tabella | Scrittori di oggi |
|---|---|
| `mike_activity` | `Betfair/mike/db.py:76` |
| `omega_activity` | `Betfair/omega/omega_db.py:63` |
| `safe_strategy_activity` | `Betfair/safe_strategy/bot_db.py:89` |
| `tennis_bot_activity` | `Betfair/stream/tennis_live/tennis_db.py:521` |
| `scalper_activity` | `Betfair/stream/scalper/scalper_service.py:86,893`; `scalper_session.py:1410,1421` |
| `live_alerts` | `Betfair/stream/db.py:697`; `motore_ordini.py:2583`; `live_order_worker.py:1071`; `scalper_session.py:714,999,1215,1839,2222`; `scalper_service.py:671` |
| `betfair_live_journal` | `Betfair/stream/db.py:988`; `live_order_worker.py:1134` |
| `betfair_live_audit` | `Betfair/stream/live_order_worker.py:922`; `daily_stop_worker.py:391` |
| `signal_history` | `Betfair/money_management.py:2434,2471` (upsert su `signal_id`) |
| `live_run_log` | `Betfair/stream/db.py:644` (upsert su `event_id`) |
| `theta_confirm_requests` | `scalper_session.py:2083-2105`: NON e' un log (insert che restituisce `id`, poi update per `id`): fuori da T8 (par. 9) |

Apertura per processo (nomi unici: `runner-calcio`, `runner-tennis`, `mike`, `omega`, `safe`, `scanner`, `tennis-bot`,
`scalper-<event_id>`) nel `main` di ciascuno, accanto a `usa_timeout_bot()` (`mike/service.py:7435`, `omega_service.py:8815`,
`bot_service.py:10871`, `safe_strategy/service.py:3363`) e nei `main` dei runner; `postino.ferma()` poi `archivio.chiudi()`
all'arresto. `ArchivioOccupato` (doppia istanza) -> si resta su `vecchio` con allarme. La riconciliazione notturna e la
pulizia partono da sole (thread del postino e di manutenzione).
**Uguale o meglio**: `confronta_ombra(tabella, ["kind","event_id"], "ts", giorno) == []` (+/- 0) per N notti; `riconcilia`
vuoto; prova sotto carico (R08) sul replay a cadenza reale: L2/L6 p99 non peggiori oltre la variabilita' di due giri identici.

### 8.3 T14 - soldi (`ARCH_STATO_DENARO_<BOT>`)
`stream/db.py:773-1189` (specchio con `rev_colonna=updated_at`, posizioni, regolati, battito coalescente), poi
`mike/db.py:175-288`, `omega_db.py:75-280`, `bot_db.py:91-264`, `tennis_db.py:532-640`; in ombra SOLO `<tabella>_ombra`
(gia' nella migrazione); trade solo dopo U-80; «prima la riga, poi l'invio» con `archivio.conferma()`.

## 9. Divergenze per l'utente, rischi, dubbi

1. **Istante dei log** (da approvare): oggi `ts`/`created_at` = `now()` del cloud all'insert; col postino = istante
   dell'evento timbrato dall'archivio (uguale a meno della latenza di rete; ore di differenza se il cloud era fermo, cioe'
   l'istante GIUSTO). E' «meglio», ma e' una differenza.
2. **`theta_confirm_requests`** e' un comando (id restituito poi update per id): come i trade (R01/U-80) non passa al
   postino senza identita' locale; propongo di toglierla da T8.
3. **`signal_history`** ha gia' la chiave `signal_id` (upsert): il suo `uid` (U-50) e' innocuo ma ridondante.
4. **Canale locale**: i bot oggi pubblicano la riga SCRITTA con l'`id` del cloud (`mike/db.py:77-78` `pubblica_scritte`);
   col postino la riga locale non ha `id` (ha `uid`): i lettori della UI che usano `id` vanno verificati prima di T8 (J).
5. **«Il log non ferma mai il bot»** (`mike/db.py:79-80`): `scrivi` non solleva per la rete ma solleva per errori del
   chiamante (tabella non registrata, chiave mancante): l'aggancio tiene il `try/except` che logga.
6. **GIL (R08)**: in laboratorio a 600 righe/s il ciclo CPU rallenta (383 -> 244 giri/s); a 60 righe/s e' nella
   variabilita' in 2 ripetizioni su 3. Prova vera sul PC in T8; se peggiora, U-82.
7. **U-55**: nel container un file e due file non si distinguono al p99; da ripetere sul PC con `misura_g1.py`.
8. **Windows non provato qui**: `msvcrt.locking` del lucchetto, cancellazione di un JSONL aperto, `%LOCALAPPDATA%`: i test
   girano sul PC con la suite.
9. **Valori proposti** (da approvare): conservazione locale 30 giorni (denaro), 2 (vivo), 3 (log) DOPO consegna E
   riconciliazione; tetto di disco 2 GB; 12 tentativi per riga transitoria (~10 min); riconciliazione dopo le 03:00 UTC.
10. **Group commit** del denaro: eventi arrivati insieme condividono un commit, ognuno confermato solo dopo il SUO
    commit (stessa garanzia di «1 commit per evento», meno fsync).
11. **«In piu' nel cloud»** ha senso solo dove il processo e' l'unico scrittore della tabella (per `live_alerts`, che
    scrivono piu' processi, va letto col registro `scrittori_oggi`).
12. **Nota di processo**: la cartella scratchpad e' CONDIVISA fra gli agenti. Un mio lancio della suite (fermato da me
    dopo pochi secondi) ha aperto in scrittura `scratchpad/suite1.txt`, nome usato anche da un altro agente, e l'ha
    troncato per un istante. Da li' in poi solo `scratchpad/w1g1/`. Al coordinatore: nomi di file unici per agente.
13. `stato()` rilegge la coda dei JSONL a ogni chiamata: con un giorno intero offline (decine di MB) costa decine di ms;
    va bene per la UI a qualche secondo, da ottimizzare (contatore incrementale) se la si chiama piu' spesso.
