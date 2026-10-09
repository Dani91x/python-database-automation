# REFERTO W1-G1 - Comparto G: archivio locale invisibile e postino (ondata 1, 09/10/2026)

Ramo `architettura/w1-g1` da `559a96df`. Nessun file esistente modificato: solo file NUOVI del dominio W1-G1.
Doc del comparto: `Betfair/nucleo/dati/doc/G1_ARCHIVIO_POSTINO.md`. In questa cartella: `misura_g1.py` + `misure_g1.txt`,
`mutazioni.py` + `mutazioni.txt` (dopo la revisione; sostituiscono `mutazioni_g1.*`).

**La revisione indipendente di `5164d6e1` ha detto DA CORREGGERE: le correzioni sono nella sezione 10, in fondo.
Le sezioni 1-9 descrivono la prima consegna; dove la revisione le ha cambiate, vale la sezione 10.**

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


## 10. Correzioni dopo la revisione (revisione indipendente di `5164d6e1`: DA CORREGGERE)

Metro dichiarato dal coordinatore: (a) il cloud non perde NESSUN dato rispetto a oggi; (b) il DB locale e' invisibile e
totalmente automatico, l'utente non interviene mai. Commit NUOVO sopra `5164d6e1` (nessuna riscrittura, nessun push).
Prove del revisore (`scratchpad/rev-w1g1/`): 21 rosse sul codice di `5164d6e1`, **tutte verdi** dopo le correzioni,
ASSERT invariati, incorporate in `Betfair/nucleo/dati/tests/test_g1_revisione.py` (35 test) con nomi che dicono il
comportamento giusto; meccanismi di prova cambiati e dichiarati in testa al file (D8: `monkeypatch` di `time.sleep` al
posto della sovrascrittura globale senza ripristino, e scrittore trattenuto perche' claim e vivo finiscano nello stesso
lotto in modo deterministico; E5: collegamento simbolico saltato dove non permesso; E8: solo POSIX). Prove mie nuove in
`test_g1_correzioni.py` (11) e in `test_g1_pg_reale.py` (+6 sul PostgreSQL vero).

sha256 dei file dopo le correzioni (prefisso; gli stessi di `mutazioni.txt`, file ripristinati identici dopo ogni
mutazione): `archivio.py` `cc7b8e1e1aace38f`, `postino.py` `90129c99867c11f1`, `schema_locale.py` `92a42e260004a391`,
`riconcilia.py` `116e3f38169ba61c` (invariato), `percorso.py` `906480ce5510683d` (invariato), migrazione `14492e4f19ad5604`.

| Punto | Correzione (file:riga) | Test (verde ora, rosso prima) | Mutazione rossa |
|---|---|---|---|
| **A1** riga velenosa | `postino.py:151` `_valida_json` + `:547`: NaN/Infinity/surrogato -> dead_letter `dato` PRIMA della chiamata; `:561-580` bisezione su errore di dato di tutta la chiamata (`\u0000` -> 22P05) fino alla riga sola; testi salvati SOLO ASCII (`schema_locale.py:205` `testo_json`): `chiudi_log` non solleva piu' con un surrogato | `test_rev_D1_*`, `test_rev_D1b_*`, `test_A1_carattere_nullo_*`, `test_pg_A1_carattere_nullo_*` (PostgreSQL vero, 22P05), `test_pg_A1_nan_*` | N11, N12 |
| **A2** scrittore piantato | `archivio.py:559` `_esegui_con_ritento`: errore di dato -> isolamento subito, altri errori dopo 3 tentativi; `:662` `_isola` voce per voce; `:683` `_veleno` -> `scarti_scrittore.jsonl` (fsync), evento `dati.dead_letter` fonte `scrittore`; l'I/O si ritenta per sempre (`:142-153` `errore_di_dato`/`errore_di_io`) | `test_rev_D2_*`, `test_A2_versione_oltre_2_alla_63_*`, `test_A2_chiave_con_surrogato_*` | N01, N02 |
| **A3** riparazione log | `archivio.py:864` `_ripara_log_troncati`: ultimo `\n` cercato all'indietro a blocchi di 1 MiB fino all'inizio; taglio a 0 SOLO se il file non ha nessun `\n`; l'evento riporta i byte veri | `test_rev_D4_*` (2 MB buoni + 1,3 MB di coda: i 2 MB restano, byte = frammento), `test_rev_D4b_*` (tutto frammento -> 0) | N03 |
| **A4** dead_letter che non rientrano | `postino.py:110` `classe_riga`: `dato` = classe 22 e 23 tranne 23503; `schema` = 42/0A/GP001 -> tabella bloccata, segnalata UNA volta (`:645` `_blocca`), mai dead_letter; resto transitorio, `:83` tetto 360 tentativi (~6 h); `archivio.py:959` `rientro_dead_letter` chiamato da `postino.py:269` ogni minuto: transitorie ogni 15 min, `dato`/`registro` ogni 24 h (`archivio.py:131`), SENZA tetto di rientri (colonna `rientri`, schema v2 `schema_locale.py:105`) | `test_rev_D9_*` (25006, 53100, 08006, 57P02), `test_rev_D9b_*`, `test_rev_D10_*` (40 min, nessuna dead_letter), `test_A4_*` (3), `test_pg_A4_colonna_sconosciuta_*` | M12, M13, M21, N13, N14 |
| **M1** tabella non registrata | `postino.py:274-280`: voce di outbox o di log di una tabella sconosciuta -> dead_letter `registro` (rientra ogni 24 h), le altre tabelle proseguono; `riconcilia_giorno` la salta | `test_rev_D3_*`, `test_rev_D3b_*` | N15 |
| **M2** marcatore oltre la fine | `postino.py:371` `_marcatore_valido`: offset > dimensione O prima riga diversa (firma, `schema_locale.py:211`, colonna `consegna.firma` dello schema v2) -> marcatore a 0 (`archivio.py:992` `azzera_marcatore`) + segnalazione + evento; ritento sicuro per `uid` | `test_rev_D5_*`, `test_rev_D5b_*` (file sostituito gia' piu' lungo del marcatore) | N04, N05 |
| **M3** versione uguale o piu' vecchia | SCELTA: `archivio.py:769` `_versione` + `:1281` `_stantia`: uguale o piu' vecchia fino a 5 s (`:125`) -> "precedente + 1 us" e vince (come l'ultimo upsert di oggi); oltre (o intero piu' basso) -> stantia, scartata con `dati.riga_vecchia`; SQL: esito `vecchia` (migrazione :334) e evento per riga nel postino (`postino.py:592`); `>` stretto nel SQL (le versioni arrivano monotone) | `test_rev_D6_*` (stesso `updated_at`: EXECUTION_COMPLETE vince), `test_rev_D6b_*` (-3 s), `test_rev_M3_*`, `test_M3_versione_intera_*`, `test_rev_R13_*`, `test_pg_versione_mai_indietro` (`vecchia`) | M03, N06, N07, N23, R13, S04 |
| **M4** ordine per chiave | `postino.py:509` `_consegna_gruppo`: una voce per chiave per chiamata, le voci di una chiave fallita aspettano (`:520`); `archivio.py:919` `outbox_pronta` FIFO per chiave fra un giro e l'altro | `test_rev_D11_*`, `test_rev_D11b_*`, `test_M4_*` | N08, N09, N10 |
| **M5** claim idempotente | `archivio.py:582` `_esegui_unita`: tre unita' indipendenti (log, denaro, vivo), si ritenta solo quella fallita; `:655` `_parte` + `:525` `_attendi`: un lavoro scaduto prima di partire si annulla (esito vero: non avvenuto), se partito si aspetta l'esito vero; `conferma` = soglia contigua (`:456`, `:754`) | `test_rev_D8_*` (claim vero = True), `test_rev_M5_*`, `test_R8_commit_del_vivo_*` | N16, N17, R6 |
| **M6** chiusura con disco guasto | `archivio.py:698` `_salva` -> `salvataggio-*.jsonl` (fsync); `:719` `_riprendi_salvataggi` all'apertura dopo | `test_rev_E10_*` (20 accettate -> 20 in outbox dopo la riapertura, file tolto) | N18 |
| **M7** pulizia a pezzi | `archivio.py:1207` `_pulisci_righe`: chiavi candidate lette dal lettore, DELETE di 1.000 righe per lavoro (`:129`); spazio restituito a pezzi di 500 pagine | `test_rev_E9_*` (600.000 righe: `conferma()` sempre sotto 1 s) | N24 |
| **B1** auto_vacuum | `schema_locale.py:149` `assicura_auto_vacuum`: con il WAL acceso serve un `VACUUM` (istantaneo su file nuovo, una volta su file vecchio) | `test_rev_E3_*` (=2 e il file si restringe a meno della meta' dopo la pulizia) | N21 |
| **B2** upsert sempre completi | SCELTA: upsert = FUSIONE delle colonne (come l'upsert di PostgREST di oggi) in locale (`archivio.py:785` `_applica`), in `leggi` (`:392`) e nella coalescenza (`:809` `_in_outbox`); nessun rifiuto in `scrivi` | `test_rev_D7_*` | N19, N20 |
| **B3** `apri()` e `OSError` | documentato in testa al modulo e in `apri` (l'aggancio resta su "vecchio") | `test_rev_E6_*` (documenta) | - |
| **B5** indice unico | nota operativa in testa alla migrazione (:40-47): fuori dagli orari di trading, o CONCURRENTLY a mano prima del file | - (documentazione) | - |
| **B7** `stato()` | `postino.py:423` `_conta_log` incrementale (solo le righe nuove e quelle appena consegnate) | `test_B7_*` | N22 |
| **R10** tetti nei test | ogni `while p.drena(...)` ora e' un `for` con tetto di 200 giri | - | - |

**Mutanti sopravvissute del revisore** (R1, R7, R8, R12, R13): ora ROSSE. R1, R7, R13 con i test del revisore
(`test_rev_R1/R7/R13_*`); R8 con `test_R8_unita_di_log_fallita_dopo_il_flush_*` (flush che scrive e poi fallisce: senza
riavvolgimento il file ha doppioni) e `test_R8_commit_del_vivo_fallito_*`; R12 con `test_pg_R12_*` (patch con versione
piu' vecchia sul PostgreSQL vero: `vecchia`, cloud intatto). R11 con `test_pg_R11_*`.

**Mutazioni** (`mutazioni.py --sql`, uscita `mutazioni.txt`): **73/73 ROSSE**, ogni file ripristinato con sha256 identico:
30 della consegna riscritte sul codice corretto (M01-M30) + 3 SQL della consegna (S01-S03) + le 14 del revisore
(R1-R14, di cui R11/R12 sul SQL) + 26 nuove (N01-N24, S04, S05). Due nuove sopravvivevano al primo giro (N07: con
versioni ISO l'"uguale" e la tolleranza coincidono, mancava un test con versione INTERA; N17: D8 dipendeva dai tempi):
test aggiunto/reso deterministico, poi rosse.

**Prova di crash con SIGKILL casuali** (C1 del revisore, `test_g1_crash.py::test_sigkill_casuali_*`: archivio + postino +
riconciliazione + pulizia insieme, `p.kill()` a caso): 14 cicli seme 7 -> **5.375 righe confermate, 0 perse**, 0 doppioni
nel cloud, 0 dead_letter; 14 cicli seme 3 -> **8.050 confermate, 0 perse** (6 cicli di serie nella suite).
Differenza dichiarata: l'attesa a caso (0,4-2,2 s) parte quando il figlio e' PRONTO; con l'attesa dal lancio il figlio
(import di supabase ~1,4 s, avvio ~2,3 s in questo container) moriva prima di scrivere e la prova del revisore, cosi'
com'era, falliva a vuoto (nessun `cloud.json`) e non provava nulla.

**Test del comparto**: con il PostgreSQL usa-e-getta **113 verdi**; senza **102 verdi + 11 saltati** (i test PG).
Migrazione applicata DUE volte senza errori sul PostgreSQL 16 usa-e-getta (ricreato, poi fermato e cancellato).

**Divergenze nuove per l'utente** (in aggiunta al par. 9):
14. **Riga velenosa** (NaN, Infinity, surrogato, `\u0000`): oggi httpx/PostgREST la rifiutano e la riga si PERDE con un
    warning; col postino va in dead_letter locale (motivo `dato`), visibile, e rientra da sola ogni 24 h.
15. ~~**Versione** (M3): una riga con versione uguale o fino a 5 s piu' vecchia vince e il suo `updated_at` diventa
    "precedente + 1 us"; oltre 5 s e' considerata stantia e scartata con un evento.~~ RITIRATA dalla terza revisione
    (par. 11, R1): resta solo la 15-bis, piu' piccola.
16. **Upsert = fusione**: identico all'upsert di oggi nel cloud; in locale la riga e' la fusione delle colonne scritte.
17. **Dead_letter visibili** (aggancio proposto, NON fatto: nessun file esistente toccato): nel thread del postino, dopo
    ogni giro, `Betfair/monitor/sonde.py:167` `valore("dati", "dead_letter", stato.dead_letter)`, `valore("dati",
    "in_coda", ...)`, `valore("dati", "offline_s", ...)` e, dall'ascoltatore degli eventi, `sonde.conta("dati_eventi",
    nome)` (`:151`) per `dati.dead_letter`, `dati.postino_bloccato`, `dati.riga_vecchia`: la pagina Salute e il referto
    di `Betfair/monitor/referto.py` li mostrano gia' come valori e contatori; soglia d'allarme proposta: `dead_letter > 0`.

### 10-bis. Misure dopo le correzioni

`misura_g1.py <tmp> 3000 3` rilanciato sul codice corretto (uscita `misure_dopo_revisione.txt`; container condiviso con
gli altri agenti, NON il PC). Microsecondi.

| Cosa | Prima (`5164d6e1`) | Dopo le correzioni |
|---|---|---|
| accodamento p50 denaro / vivo / log | 12,4-13,5 / 11,2-11,4 / 18,4-18,5 | 18,4-25,0 / 16,3-16,7 / 21,3-43,8 |
| accodamento p99 denaro / vivo / log | 66-77 / 43-62 / 166-1.424 | 102-143 / 72-124 / 124-775 |
| commit denaro (FULL, lotti) p50 / max | 1,6-5,9 ms / 31-53 ms | 1,6-2,2 ms / 4,6-7,4 ms |
| commit vivo (NORMAL, lotti) p50 / max | 0,19-0,32 ms / 5,8-22,8 ms | 0,25-0,30 ms / 1,0-11,8 ms |
| checkpoint nel commit (default): max del commit del vivo | 25,8-39,0 ms | 21,8-26,4 ms (fuori dal commit: 1,0-11,8 ms) |
| R08: giro CPU, p99 spento / acceso 60 righe/s / acceso 600 righe/s | 227-300 / 257-342 / 314-603 | 292-391 / 265-309 / 318-405 |
| R08: cadenza giri/s spento / 600 righe/s | 383-406 / 228-249 | 419-441 / 263-272 |

Lettura onesta: il costo dell'accodamento e' SALITO di ~5 us al p50 per lo stato (la vista di `leggi` ora FONDE le colonne
e salva il JSON solo ASCII: B2, A1/A2) e varia molto per i log fra ripetizioni (21-44 us: macchina condivisa). Resta sotto
i 50 us al p50 ma sopra i "~15 us" di 04 par. 6.1: da rimisurare sul PC; se serve, la vista di `leggi` puo' riusare il
JSON gia' prodotto (risparmio stimato ~5 us, non fatto per non toccare il codice dopo le mutazioni). Il commit e la
contesa del GIL (R08) non peggiorano; a 60 righe/s il giro acceso sta dentro la variabilita' dello spento.

### 10-ter. Suite intera dopo le correzioni

`python -m pytest Betfair/ -q -p no:cacheprovider`, UNA volta alla fine, sul codice definitivo:
**11.673 passed, 98 skipped, 6 xfailed, 0 failed** in 525 s (i 98 saltati comprendono gli 11 di `test_g1_pg_reale.py`
senza `G1_PG_PSQL`). Prima delle correzioni: 11.626 passed, 92 skipped. I test G1 sono stati rilanciati dopo la nota
del coordinatore sul `pkill -f` del revisore (tutti verdi).


## 11. Terza revisione (seconda revisione di `a151a38a`: PASSA con 4 riserve)

Commit NUOVO sopra `a151a38a` (nessuna riscrittura, nessun push). Principio vincolante del coordinatore: **IDENTICO A
OGGI** - oggi vince l'ultima scrittura fatta dal bot e nessuna scrittura viene scartata; la versione serve SOLO a impedire
che una voce VECCHIA della STESSA origine (ritento del postino, rientro da dead_letter, voce ripetuta dopo un crash)
sovrascriva una voce piu' nuova della stessa origine; mai scartare una scrittura nuova del bot per l'orologio.

sha256 dei file consegnati (prefisso; gli stessi di `mutazioni.txt`, ogni file ripristinato identico dopo ogni
mutazione): `archivio.py` `e05a3f1e7b9bfd89`, `postino.py` `09d59f49d4a57a08`, `schema_locale.py` `77e3078b878ca798`, `riconcilia.py` `116e3f38169ba61c` (invariato), `percorso.py` `906480ce5510683d` (invariato), migrazione `3ed0741942c15fdd`.

| Riserva | Correzione (file:riga) | Test (verde ora) | Mutazioni rosse |
|---|---|---|---|
| **R1** (MEDIO) orologio indietro > 5 s: aggiornamenti scartati | Tolti `TOLLERANZA_OROLOGIO_US`, `_versione`, `_stantia`, `_sali_rev` e il "+1 us". `archivio.py:531` `_metti`: numero d'ordine, `vseq` LOCALE del file e accodamento sotto UN lucchetto (l'ordine delle vseq e' l'ordine in cui lo scrittore applica); `:672` `meta.vseq` alzato nella STESSA transazione delle righe (mai riusata; schema v3 `schema_locale.py:115`: `meta`, `vseq` su righe/outbox/dead_letter); `:547` `origine()` = processo/regime/id casuale del file; `:858` `_applica`: vince SEMPRE l'ultima accodata (fusione), valori del bot TALI E QUALI; `:455` `transizione` cambia solo `status`, con la sua vseq. Postino `postino.py:587` manda `p_origine` e `p_versioni`. Migrazione `:214` `public.postino_versioni` (tabella, chiave tipata, origine -> versione piu' alta), `:245` RPC con firma nuova (`DROP` della vecchia: non ancora applicata): `:360` piu' vecchia della STESSA origine -> `vecchia`, uguale -> `ignorata`, origine diversa -> scritta (vince l'ultima arrivata); `:395` versione registrata nella stessa sottotransazione della riga; `:329` versioni oltre 90 giorni tolte (100 per chiamata) | `test_g1_terza_revisione.py::test_R1_orologio_indietro_115_s_*` (m3.py scenario 4: EXECUTION_COMPLETE in locale e nel cloud, `updated_at` 10:00:05 tale e quale), `test_R1_esito_vecchio_di_3_s_*` (scenario 1), `test_R1_ritento_di_una_voce_gia_superata_*`, `test_R1_due_processi_vince_l_ultima_arrivata` (scenario 2, piu' il ritento vecchio di A scartato dopo B), `test_R1_vseq_persistita_*`; PostgreSQL vero: `test_pg_versione_per_origine_mai_dall_orologio`, `test_pg_R12_*_stessa_origine_*` | M03, N06, N07, N20, N23, R13, V08r, V09r, V10r, T01-T05, S01, S04, S06, S07, R12 |
| **R2** (MEDIO-BASSO) dead_letter transitoria che rientra e riporta indietro il cloud | (a) `archivio.py:1075` `rientro_dead_letter`: la riga rientra con la SUA vseq; se la chiave ha una vseq piu' alta nella riga locale o in outbox e' SUPERATA: resta archiviata con la nota, evento `dati.dead_letter_superata`; seconda difesa nel cloud (`postino_versioni`: `vecchia`). (b) `:1038` `chiudi_voci`: una `dato` che muore dopo `RIENTRI_MAX_DATO` = 7 rientri (`:150`, uno ogni 24 h) nasce ARCHIVIATA (`archiviata_ms`, nota "rientri esauriti", evento `dati.dead_letter_archiviata`), esce dal conteggio d'allarme (`:1013`), non rientra piu'; `postino.py:109` `StatoPostinoArchivio` (sottoclasse di `StatoPostino`, campi del contratto invariati) con `archiviate`. Le transitorie e quelle di registro rientrano per sempre (dichiarato). (c) `archivio.py:1329` `pulisci`: archiviate tolte dopo `CONSERVA_ARCHIVIATE_GIORNI` = 30 (`:153`), a pezzi, mai le attive | `test_R2a_dl_stale_*` (dl_stale.py del revisore: il cloud resta NUOVO), `test_R2a_anche_senza_la_riga_locale_*` (seconda difesa), `test_R2b_dato_archiviata_dopo_N_rientri_*` (7 rientri, poi `(dead_letter, archiviate) = (0, 1)` e nessuna chiamata in 3 giorni), `test_R2c_pulisci_*`; PostgreSQL vero: `test_pg_R2a_dl_stale_*` | V05, T02, T06-T12, S08 |
| **R3** (BASSO) scarti senza rientro, `errore_di_dato` troppo largo | `archivio.py:168` `errore_di_dato` SOLO casi provati (UnicodeEncode/DecodeError, OverflowError, IntegrityError, DataError, JSON guasto); `:181` `errore_di_codice`; `:711` `_isola`: errore di codice = voce SOSPETTA (le voci della stessa chiave aspettano dietro), se nessuna voce passa e' un guasto del codice: `:759` `_guasto_codice` (niente scarti, voci in coda, CRITICAL al piu' una volta al minuto, contatore `guasti_codice`, evento `dati.archivio_guasto_codice`, esposti in `stato()`); se le altre passano, la sospetta va negli scarti. Scarti: nell'allarme 7 giorni, poi fra le archiviate (`:1027`), tolti dalla pulizia dopo altri 30 (`:1365`) | `test_R3_errore_di_dato_solo_i_casi_provati`, `test_R3_errore_di_codice_su_tutte_le_voci_*` (TypeError su ogni scrittura: 0 scarti, 1 CRITICAL in piu' giri, poi tutto confermato), `test_R3_errore_di_codice_su_una_sola_voce_*`, `test_R3_scarti_nell_allarme_poi_archiviati_poi_tolti_*` | N02, T13-T19 |
| **R4** (test mancante) V14 sopravvissuta | nessuna correzione del codice (`archivio.py:623`: il salvataggio solo `if self._in_chiusura`): mancava la prova. `ATTESA_RITENTO_BASE_S` (`:139`) dichiarata per accorciare l'attesa nel test | `test_R4_disco_guasto_per_3_o_piu_tentativi_poi_ripristino_a_processo_vivo` (disco_guasto.py del revisore: COMMIT del denaro guasto per 5+ tentativi con un claim e un `accoda` in corso; il disco torna; claim VERO, `accoda` con il seq, tutto confermato, nessun `salvataggio-*.jsonl`) | V14 |
| Prova SIGKILL fragile | `test_g1_crash.py` modo "finale": finestra ADATTIVA, si drena finche' la coda scende e ci si ferma solo se non scende per 60 s (`G1_FERMO_S`); tetto di sicurezza del figlio 3.600 s. Il cloud finto persistente salva anche `postino_versioni` (come il vero) | `test_sigkill_casuali_nessuna_riga_confermata_persa` | - |

**Prove cambiate perche' il comportamento richiesto e' cambiato** (asserzioni riscritte sul principio "identico a oggi",
dichiarate): `test_leggi_vede_subito_e_versione_mai_indietro` (la scrittura con `updated_at` 65 s piu' vecchio ora VINCE;
una riga senza `updated_at` si scrive, come oggi), `test_transizione_cambia_solo_lo_stato_e_alza_la_vseq_locale` (era
`test_transizione_alza_la_versione`: `updated_at` non si tocca piu'), `test_rev_D6b_*` (`updated_at` tale e quale),
`test_rev_M3_orologio_indietro_di_9_s_vince_l_ultima_scritta` (era `..._scartata_con_evento`), `test_rev_R13_leggi_vede_l_ultima_scritta_*`,
`test_M3_versione_intera_vince_sempre_l_ultima_scritta_tale_e_quale`, `test_riga_vecchia_tardiva_*` (ora la voce vecchia e'
della STESSA origine), `test_finto_semantica_versione_e_vincoli`, `test_pg_versione_per_origine_*` e `test_pg_R12_*` (RPC
nuova). `test_A2_versione_oltre_2_alla_63_*`: la versione non va piu' in una colonna INTEGER, quindi l'`OverflowError` di
SQLite si provoca con un involucro della connessione (stessa eccezione); `pulisci()` ritorna le stesse chiavi di prima, i
conteggi nuovi sono in `contatori` (`archiviate_tolte`, `scarti_tolti`).

**Riletture del materiale del revisore** (`scratchpad/rev_w1g1_2/`, lanciato sul codice nuovo): `m3.py` -> scenario 1 e
1b: locale e cloud EXECUTABLE con `updated_at` tale e quale; 2: cloud EXECUTABLE (B, l'ultimo arrivato, come oggi); 3:
EXECUTION_COMPLETE; 4: EXECUTION_COMPLETE con 10:00:05, nessun evento. `dl_stale.py` -> cloud dopo il rientro del VECCHIO:
`[('NUOVO', None)]`, evento `dati.dead_letter_superata`. `disco_guasto.py` -> claim bloccato 12 s col disco guasto, poi
`True` dopo il ripristino.

**Mutazioni** (`mutazioni.py --sql`, uscita `mutazioni.txt`): **111/111 ROSSE (101 Python + 10 SQL sul PostgreSQL usa-e-getta)**, ogni file ripristinato con sha256 identico.
Le 16 del revisore (V01-V16) si giudicano come le giudicava lui, su TUTTI i test G1; V04, V05, V15 riportate sul codice
nuovo (stesso difetto); V08, V09, V10 mutavano la tolleranza e il "+1 us" che R1 ha TOLTO: sostituite da V08r (la versione
mandata al cloud torna a essere l'orologio del bot), V09r (vseq che non sale), V10r (transizione con una versione vecchia).
Nuove della terza revisione: T01-T19 e S06-S08; riscritte sul codice nuovo: M03, M09, M27, N02, N06, N07, N20, N23, R13,
S01, S03, S04, R12.

**Prova di crash con SIGKILL casuali**: 14 cicli seme 7 -> **4.325 righe confermate, 0 perse** (0 uid, 0 ordini, 0 eventi mancanti o indietro), 14 cicli seme 3 -> **5.225 confermate, 0 perse**; 0 doppioni, 0 dead_letter (6 cicli di serie nella suite).

**Test del comparto**: con il PostgreSQL usa-e-getta **129 verdi**; senza **117 verdi + 12 saltati** (i test PG). Migrazione applicata DUE volte senza errori sul PostgreSQL 16 usa-e-getta (ricreato per questa revisione, poi fermato e cancellato).

**Divergenza #15 (par. 10) RITIRATA**: non c'e' piu' alcun "+1 us" ne' scarto per l'orologio; una scrittura del bot vince
sempre in locale e, fra processi diversi, vince l'ultima arrivata nel cloud, come oggi. Resta una sola differenza, piu'
piccola e dichiarata: **15-bis** una voce vecchia della STESSA origine che il postino ritenta o fa rientrare DOPO che una
voce piu' nuova della stessa chiave e della stessa origine e' gia' arrivata NON si riapplica (oggi un ritento del genere non
esiste: la riga persa resta persa, quindi non e' una perdita rispetto a oggi).
**Divergenze nuove**: 17. le dead_letter di dato dopo 7 rientri (una settimana) diventano archiviate: niente piu'
allarme ne' chiamate, restano 30 giorni su disco; 18. gli scarti dello scrittore restano nell'allarme 7 giorni, poi
archiviati, tolti dopo altri 30; 19. tabella nuova nel cloud `public.postino_versioni` (una riga per tabella, chiave e
origine, toccata a ogni consegna di stato: il costo di una scrittura in piu' per riga nella RPC); 20. residuo dichiarato:
una dead_letter TRANSITORIA (rientra per sempre) che resta morta oltre 90 giorni e la cui riga locale e' gia' stata pulita
perde la seconda difesa (versione tolta dal cloud): il caso richiede un padre assente per tre mesi.

### 11-bis. Suite intera dopo la terza revisione

`python -m pytest Betfair/ -q -p no:cacheprovider`, UNA volta alla fine, sul codice definitivo (PostgreSQL usa-e-getta gia'
fermato): **11.688 passed, 99 skipped, 6 xfailed, 0 failed** in 394 s (i 99 saltati comprendono i 12 di
`test_g1_pg_reale.py` senza `G1_PG_PSQL`). Le 2 avvertenze di thread vengono da `cambio-gbp-eur`, fuori dal comparto G.

## 12. Per W1-C1 (porta ordini)

Semantica di `transizione` verificata dal revisore (`transizione.py`) e provata da
`test_g1_terza_revisione.py::test_C1_semantica_dichiarata_di_transizione` e `test_R4_*`:
- riga assente -> `False`; colonna di stato diversa da `da` o assente -> `False`; secondo claim uguale -> `False`; tabella
  di log -> `ValueError`; tabella non registrata -> `KeyError`;
- cambia UNA colonna sola, `status`; le altre (`updated_at` compreso) restano tali e quali; la voce porta la sua vseq;
- vede tutte le scritture accodate prima (anche non ancora su disco): la esegue il thread di scrittura;
- atomicita' LOCALE (riga e outbox nella stessa transazione, un solo scrittore per archivio): NON e' un lucchetto fra
  processi;
- durabilita' PIENA (`synchronous=FULL`) SOLO sul regime `stato_denaro`; sul `stato_vivo` un claim confermato puo'
  perdersi a PC spento;
- con il disco guasto il chiamante resta bloccato finche' il disco non torna, poi riceve l'esito VERO (mai un esito
  falso); l'unica eccezione e' il lavoro che scade PRIMA di partire: `TimeoutError` "annullato prima di partire (non
  eseguito)", che e' l'esito vero.
- Le tabelle della porta (`ordini_ref_visti`, `ordini_seq`) vanno REGISTRATE nel registro con regime `stato_denaro`.


## 13. Quarta revisione (revisione mirata di `eef92315` su PostgreSQL vero: PASSA, con la riserva D e le note a, b)

Esito del revisore: 8 scenari su 8 identici a oggi, RPC sicura (SECURITY INVOKER), migrazione idempotente, 111/111
mutazioni mie rosse e 10/11 delle sue rosse. Commit NUOVO sopra `eef92315` (nessuna riscrittura, nessun push).
Materiale: `scratchpad/rev_w1g1_3/` (`origine.py`, `origine_2d.py`, `ordine_vseq.py`, `mie_mut.py`, `conc_a/b.sql`).

sha256 dei file consegnati (prefisso; gli stessi di `mutazioni.txt`): `archivio.py` `1861f2a7695f5a10`, `postino.py` `a621eee89057ce84`, `schema_locale.py` `28dd4d3b232a5972`, `riconcilia.py` `116e3f38169ba61c` e `percorso.py` `906480ce5510683d` (invariati), migrazione `dc7069ba44cddafc`.

| Punto | Correzione (file:riga) | Test (verde ora) | Mutazioni rosse |
|---|---|---|---|
| **D** perdita di corrente sullo `stato_vivo` (NORMAL): vseq riusata con la stessa origine, la scrittura nuova del bot scartata come `vecchia` | `archivio.py:341` `apri()`: origine NUOVA a ogni apertura (id casuale, scritto in `meta.origine`); ogni voce di outbox nasce con l'origine dell'apertura (`:897` `_in_outbox`, colonna `origine` dello schema v4 `schema_locale.py:132`), la dead_letter la copia (`chiudi_voci`), il rientro e `rimetti_in_coda` la conservano; `postino.py:539` `_consegna_gruppo`: una chiamata porta voci di UNA origine (le voci senza versione vanno con tutte); una voce di un'altra origine passa al pezzo dopo e la sua chiave resta FERMA nel pezzo (FIFO per chiave intatto); `:594` `p_origine` e `p_versioni` dalla voce. Il controllo "superata" confronta la vseq LOCALE del file (monotona fra le aperture): vale anche fra origini diverse | `test_g1_quarta_revisione.py::test_D_perdita_di_corrente_sul_vivo_la_scrittura_nuova_arriva` (scenario D del revisore: cartella riportata allo stato di prima del blackout, vseq davvero riusata = 1, il cloud passa a CLOSED con `updated_at` tale e quale; con l'origine fissa e' ROSSO: STREAMING), `test_D_voci_rimaste_in_outbox_*` (le voci di prima vanno prima, con la loro origine e la loro vseq), `test_D_rientro_superato_da_una_scrittura_di_un_altra_apertura`, `test_D_voce_rientrata_di_un_altra_origine_resta_davanti_*`; PostgreSQL vero: `test_pg_D_perdita_di_corrente_*` | T20 (origine fissa), T22, T23 |
| **nota a** invariante "ordine delle vseq = ordine di coda" sotto thread | `archivio.py:146` `GANCIO_METTI`: gancio dei test (None in produzione) chiamato in `_metti` fra l'assegnazione della vseq e l'accodamento | `test_a_ordine_delle_vseq_uguale_ordine_di_coda_anche_fra_thread` (`ordine_vseq.py` del revisore reso deterministico: il gancio ferma il primo scrittore finche' il secondo non ha finito, al massimo 0,3 s; piu' il carico del revisore 6 x 40) | T21 (X3 col gancio), X3r (X3 del revisore com'era, con lo sleep di 0,5 ms) |
| **nota b** deadlock 40P01 fra due postini con lotti in ordine opposto | migrazione `:336` la RPC scrive le righe in ordine di CHIAVE (poi di posizione); `:413` gli esiti tornano nell'ordine di `p_righe` | `test_pg_b_due_postini_lotti_in_ordine_opposto_niente_deadlock`: le due sessioni psql del revisore (300 chiamate da 10 righe, k0..k9 contro k9..k0, in parallelo): **0 deadlock, 3.000 ok per sessione** (prima: 1.071 e 953 esiti 40P01); `deadlock_timeout` 20 ms nella prova perche' la mutazione resti veloce | S09 (ordine d'arrivo: deadlock), S10 (esiti in un altro ordine) |

**Mutazioni del revisore** (`mie_mut.py`): 10/11 rosse; la sopravvissuta **X9** ("versione registrata prima della riga")
e' EQUIVALENTE: l'INSERT della versione anticipato sta nella STESSA sottotransazione (`BEGIN ... EXCEPTION`) della
scrittura della riga, quindi se la riga fallisce la versione si annulla con lei e, se la riga passa, il risultato e'
identico. Non c'e' un comportamento osservabile da rendere rosso; la variante NON equivalente (X9b, versione registrata
nel ramo dell'eccezione) e' uccisa da `test_pg_R12_*` (la riga rifiutata non lascia la sua versione: il ritento passa).

**Mutazioni** (`mutazioni.py --sql`, uscita `mutazioni.txt`): **118/118 ROSSE (106 Python + 12 SQL sul PostgreSQL usa-e-getta)**, ogni file ripristinato con sha256 identico.
Nuove: T20-T23, X3r, S09, S10; riportate sul codice nuovo: N09, T04, V10r, V15.

**Casi del revisore che restano DICHIARATI** (`origine.py`; nessuna perdita rispetto a oggi):
- **A** (2a) crash con una voce in outbox e riapertura della stessa cartella: la voce sopravvissuta tiene la sua origine e
  la sua vseq, va PRIMA della scrittura nuova della stessa chiave (FIFO), la nuova arriva per ultima: nel cloud la nuova,
  come oggi;
- **B** (2b) la voce sopravvissuta al crash arriva al cloud DOPO la riga piu' nuova di un ALTRO processo: vince come
  ultima arrivata (origini diverse). Oggi la voce del crash sarebbe persa e nel cloud resterebbe quella dell'altro
  processo: e' un dato in piu', non in meno, ma l'ultima arrivata non e' l'ultima scritta (divergenza dichiarata);
- **C** (2c) cartella cancellata: origine nuova, la outbox vecchia non c'e' piu' (come oggi le righe non ancora
  inviate di un processo morto); la scrittura nuova arriva.
**D** si chiude con questa revisione. Resta dichiarato (par. 11) il residuo #20.

**Prova di crash con SIGKILL casuali**: 14 cicli seme 7 -> **4.125 righe confermate, 0 perse**; 14 cicli seme 3 -> **4.900 confermate, 0 perse**; 0 doppioni, 0 dead_letter.

**Test del comparto**: con il PostgreSQL usa-e-getta **136 verdi**; senza **122 verdi + 14 saltati** (i test PG). Migrazione applicata DUE volte senza errori sul PostgreSQL 16 usa-e-getta (ricreato, poi fermato e cancellato).

### 13-bis. Suite intera dopo la quarta revisione

`python -m pytest Betfair/ -q -p no:cacheprovider`, UNA volta alla fine, sul codice definitivo (PostgreSQL gia' fermato): **11.693 passed, 101 skipped, 6 xfailed, 0 failed** in 427 s (i 101 saltati comprendono i 14 di `test_g1_pg_reale.py` senza `G1_PG_PSQL`). Le avvertenze di thread vengono da `cambio-gbp-eur`, fuori dal comparto G.
