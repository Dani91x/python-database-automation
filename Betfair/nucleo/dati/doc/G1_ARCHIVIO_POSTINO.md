# G1 - Archivio locale e postino (comparto G, ondata 1, agente W1-G1)

File: `percorso.py`, `schema_locale.py`, `archivio.py`, `postino.py`, `riconcilia.py` in `Betfair/nucleo/dati/`;
migrazione `migrations/architettura_uid_ombra_2026-10-09.sql` (SOLO scritta: la applica l'utente);
test `tests/test_g1_*.py`. Contratto: `contratto.py` (fisso). Referto: `ARCHITETTURA_2026-10/ondata1/W1-G1/REFERTO.md`.

## 1. Scopo

Ogni riga che oggi va al cloud passa prima da un archivio sul PC, invisibile all'utente, e arriva al cloud con un
postino DOPO la decisione, fuori dal ciclo: stessa tabella, stesse colonne, senza doppioni; se non si puo' consegnare
resta in coda con un allarme, mai scartata (ordini dell'utente del 09/10). Tre regimi misurati (04 par. 6.1):

| Regime | Dove | Durabilita' | Per |
|---|---|---|---|
| `stato_denaro` | `denaro.sqlite3`, WAL `synchronous=FULL` | anche a PC spento (doc. SQLite) | ordini, specchio, posizioni, trade |
| `stato_vivo` | `vivo.sqlite3`, WAL `synchronous=NORMAL`, lotti | crash del processo; l'ultima transazione puo' sparire allo spegnimento | ladder, live_now, battiti, follow |
| `log` | `log/AAAA-MM-GG.jsonl`, write+flush | crash del processo (07 par. 6.1: 0 persi) | attivita', allarmi, journal, audit |

Cartella: `%LOCALAPPDATA%\AlphaScore Trading\archivio\<processo>\` (Windows), `~/.local/share/alphascore-trading/archivio/`
altrove; `ARCH_ARCHIVIO_DIR` la allinea all'app desktop. Mai dentro il repo. Un lucchetto per processo.

## 2. Entrate

- `ArchivioLocale(processo, registro, ...)`: `registro` = mappa o funzione `nome -> SpecTabella` (le righe sono di W1-G2,
  `registro.py`); una tabella non registrata e' rifiutata.
- `scrivi(tabella, riga)` (asincrona: il chiamante paga copia + JSON + accodamento, ~12-20 us p50 misurati),
  `transizione(tabella, chiave, da, a)` (claim atomico), `leggi(tabella, chiave)`, `conferma(timeout_s)` (barriera di
  durabilita': «prima la riga, poi l'invio», R03), `accoda(...)` (forma sincrona con seq).
- `PostinoLocale(archivio, cloud, ombra=False, tetto_disco_mb=2048, ...)`: `cloud` e' il protocollo `Cloud` (client unico,
  W1-G2). `drena(max_righe)` (quota equa fra denaro, vivo e log: nessuna fonte affama le altre), `stato()`,
  `riconcilia(tabella, da_ts)`, `riconcilia_giorno(giorno, tabelle)`, `avvia()/ferma()` (thread `postino`: drena e,
  una volta al giorno dopo le 03:00 UTC, riconcilia il giorno prima: i marcatori `ok` abilitano la pulizia automatica
  del thread di manutenzione dell'archivio; nessun intervento dell'utente).

## 3. Uscite

- Righe nel cloud tramite UNA RPC generica `postino_consegna` (insert `ON CONFLICT DO NOTHING`, upsert con versione
  monotona `WHERE excluded.rev > t.rev`, patch, delete; esito per riga). In ombra: `<tabella>_ombra`.
- Eventi (`eventi(nome, dati)`, di serie nel log del processo): `dati.postino_offline(da)`, `dati.postino_online`,
  `dati.dead_letter(tabella, riga, errore)`, `dati.postino_bloccato(tabella, errore)`, `dati.tetto_disco` (+ segnale
  `ripiego_diretto`), `dati.riga_troncata`, `dati.archivio_guasto`/`_ripreso`, `dati.riconciliazione`.
- `StatoPostino` (in coda, eta' massima, per tabella, ultimo errore, offline da, dead_letter), `RapportoRiconciliazione`,
  `misure()` (p50/p95/p99/max di accodamento, commit, durevole-dopo, checkpoint).

## 4. Dipendenze ammesse

Solo libreria standard (`sqlite3`, `json`, `threading`) e il contratto `dati/contratto.py`. Riuso di `db_client`
(`classifica_guasto_rete`, `ATTESE_RETE_S`) con import PIGRO (solo quando serve classificare un errore: `config` legge
l'ambiente). Nessun import di supabase/httpx nel codice: il cloud arriva iniettato. Nessun import di bot.

## 5. Funzionalita' coperte (id di `01_FUNZIONALITA.md`) e test che le prova

| Id | Cosa | Test |
|---|---|---|
| G-013 (scrittura dei log, curatore: riduzione del blocco su 57014) | log via JSONL + postino; 57014 dimezza il blocco | `test_g1_postino::test_consegna_log_e_stato_stesse_colonne`, `::test_57014_dimezza_il_blocco` |
| G-014 (`insert_alert`) | `live_alerts` con FK su `live_follow`: 23503 transitorio, ordine padre/figlio | `::test_23503_*`, `::test_padre_prima_del_figlio_nello_stesso_giro` |
| G-016, G-017, G-018 (specchio, posizioni, heartbeat) | regime `stato_denaro`/`stato_vivo`, versione, coalescenza | `test_g1_archivio::test_coalescenza_*`, `test_g1_postino::test_riga_vecchia_tardiva_*` |
| G-019 (`log()` dei bot: oggi l'errore diventa warning) | dead_letter visibile, mai warning (PSB 7 n.18) | `::test_check_rifiutato_*` |
| G-021 (trade) | solo la colonna `trade_uid` e l'ombra; l'id del cloud resta (U-80) | migrazione + `test_g1_pg_reale` |
| G-023 (claim delle richieste) | `transizione` atomica | `test_g1_archivio::test_transizione_*` |
| G-004, G-005 (classificazione e attese) | riusate, non copiate | `test_g1_postino::test_guasti_di_rete_veri_*`, `::test_cloud_fermo_*` |

Restano al vecchio codice tutte (nessun aggancio in questa ondata): l'aggancio e' l'ondata 2 (T8, poi T14).

## 6. Interruttore previsto

`ARCH_POSTINO_LOG=vecchio|ombra|nuovo` (T8) e `ARCH_STATO_DENARO_<BOT>=vecchio|ombra|nuovo` (T14). In `ombra` il postino
scrive SOLO su `<tabella>_ombra` (`PostinoLocale(..., ombra=True)`); confronto con `riconcilia.confronta_ombra`.

## 7. Come si sostituisce

- Il motore locale (es. un altro database): solo `archivio.py` + `schema_locale.py`; il postino legge con 8 metodi
  (`outbox_pronta`, `chiudi_voci`, `file_log`, `offset_log`, `chiudi_log`, `conteggi_outbox`, `segnala`, `spec`).
- Il cloud (es. un altro Postgres): la RPC `postino_consegna` (una funzione SQL generica) e il protocollo `Cloud`.
- Una tabella nuova: UNA riga di registro (`SpecTabella`); nessuno schema locale nuovo, nessun `*_db.py`.

## 8. Come si prova da solo

`python -m pytest Betfair/nucleo/dati/tests -q -p no:cacheprovider -k g1` (102 verdi + 11 saltati senza PostgreSQL; 113 verdi con).
Con un PostgreSQL usa-e-getta e la migrazione applicata: `G1_PG_PSQL="-h /tmp -p 54329 -U postgres"` accende
`test_g1_pg_reale.py` (stesse prove sul SQL vero). Falsificazione: `ARCHITETTURA_2026-10/ondata1/W1-G1/mutazioni.py
[--sql]` (73 mutazioni). Crash con SIGKILL casuali: `G1_CICLI=14 G1_SEME=7` su `test_g1_crash.py -k sigkill`. Misure: `ARCHITETTURA_2026-10/ondata1/W1-G1/misura_g1.py <tmp> 3000 3`.

## 9. Misure

Nel referto (par. 4): accodamento p50 11-20 us; commit e durevole-dopo per regime; checkpoint fuori dal percorso;
un file contro due (U-55); contesa del GIL in laboratorio (R08). Misurate nel container cloud, NON sul PC: si
rilanciano sul PC con lo stesso strumento.

## 10. Voci di `PROCESSO_STANDARD_BOT.md` par. 6/7

Sollecitate: 6.3 (riavvio con stato su disco: crash con `os._exit`), 6.5 (colonne vere e CHECK veri: finti dalle
migrazioni e PostgreSQL vero), 6.6 (concorrenza: claim con 8 thread, uno scrittore), 6.7 (falsificazione: 73
mutazioni, 66 Python + 7 SQL, tutte rosse), 6.8 (referto riproducibile: comandi e strumenti); 7 n.18 (scrittura fallita mai warning: dead_letter +
evento), n.19 (stato sopravvive al riavvio), n.21 (paper e live: `mode` e' nella chiave naturale, mai sommati qui),
n.27 (finti con chiavi e tipi veri: client supabase vero), n.29-30 (test che sanno diventare rossi). Le altre sono
⊘ per il comparto (nessun ordine, nessun bot, nessun mercato): elenco con la causa nel referto par. 7.

## 11. Regole dopo la revisione indipendente (09/10)

Metro: (a) il cloud non perde NESSUN dato rispetto a oggi; (b) il DB locale e' invisibile e totalmente automatico.

- **Upsert = fusione delle colonne** (B2, scelta dichiarata): come l'upsert di PostgREST di oggi, le colonne non scritte
  restano; vale per la riga locale, per `leggi` e per la coalescenza (una voce per chiave con le colonne FUSE). Un upsert
  parziale e' quindi sicuro; nessun rifiuto in `scrivi`.
- **Versione per riga** (M3, scelta dichiarata): versione piu' nuova -> passa; UGUALE o piu' vecchia di al massimo 5 s
  (`TOLLERANZA_OROLOGIO_US`, l'orologio di Windows che torna indietro) -> diventa "precedente + 1 us" e VINCE, come vince
  oggi l'ultimo upsert; piu' vecchia oltre 5 s (versione intera: qualunque regressione) -> dato stantio, scartato con
  l'evento `dati.riga_vecchia`. Nel cloud la RPC risponde `vecchia` (evento per riga) quando la riga c'e' con una
  versione piu' nuova. Il SQL resta con `>` stretto: le versioni arrivano gia' monotone dall'archivio.
- **Scrittore** (A2, M5, M6): tre unita' indipendenti per lotto (log, denaro, vivo); la voce impossibile da salvare
  (intero oltre 2^63, chiave con un surrogato) va in `scarti_scrittore.jsonl` (fsync) e il resto prosegue; gli errori
  di I/O si ritentano per sempre; alla chiusura con il disco guasto le voci accettate vanno in `salvataggio-*.jsonl` e
  rientrano all'apertura dopo; `conferma()` e' una soglia contigua; un lavoro sincrono scaduto prima di partire si
  annulla (esito vero: non avvenuto), se e' partito si aspetta il suo esito vero.
- **Postino** (A1, A4, M1, M4): valore non JSON (NaN, Infinity, surrogato) -> dead_letter prima della chiamata; errore di
  dato su tutta la chiamata (\u0000, classe 22) -> bisezione fino alla riga sola; per riga: classe 22 e 23 (tranne 23503)
  -> dead_letter `dato`; classe 42/0A e intestazione `GP001` -> tabella bloccata, segnalata UNA volta, riga in coda;
  tutto il resto -> transitorio, ~6 h di ritenti (360 tentativi, attese fino a 60 s), poi dead_letter `transitorio`.
  **Rientro automatico** delle dead_letter: transitorie ogni 15 min, `dato` e `registro` ogni 24 h, senza tetto di
  rientri (contatore `rientri`): una migrazione che corregge un CHECK fa rientrare da sola le righe (PSB 7 n.18).
  Voce di una tabella non registrata -> dead_letter `registro`. Per chiave: al massimo una voce per chiamata, FIFO
  fra un giro e l'altro (`outbox_pronta`), le voci dopo una chiave fallita aspettano.
- **Log** (A3, M2, B7): riparazione della riga troncata cercando l'ultimo `\n` a blocchi fino all'inizio del file;
  marcatore con la firma della prima riga: oltre la fine del file o file sostituito -> torna a 0 (ritento sicuro con
  `uid`) e si segnala; conteggio della coda incrementale in `stato()`.
- **Manutenzione** (M7, B1): pulizia a pezzi di 1.000 righe (lavori di millisecondi); `auto_vacuum=INCREMENTAL`
  effettivo (VACUUM una tantum) e spazio restituito a pezzi.
- `apri()` puo' sollevare `OSError` (cartella non creabile) o `ArchivioOccupato` (B3): l'aggancio resta su "vecchio".
