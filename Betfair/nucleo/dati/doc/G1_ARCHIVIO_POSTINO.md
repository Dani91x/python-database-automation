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

- Righe nel cloud tramite UNA RPC generica `postino_consegna` (insert `ON CONFLICT DO NOTHING`, upsert = fusione delle
  colonne come oggi, patch, delete; versione LOCALE per origine, par. 12; esito per riga). In ombra: `<tabella>_ombra`.
- Eventi (`eventi(nome, dati)`, di serie nel log del processo): `dati.postino_offline(da)`, `dati.postino_online`,
  `dati.dead_letter(tabella, riga, errore)`, `dati.postino_bloccato(tabella, errore)`, `dati.tetto_disco` (+ segnale
  `ripiego_diretto`), `dati.riga_troncata`, `dati.archivio_guasto`/`_ripreso`, `dati.riconciliazione`,
  `dati.riga_vecchia`, `dati.dead_letter_archiviata`/`_superata`, `dati.archivio_guasto_codice`.
- `StatoPostino` (in coda, eta' massima, per tabella, ultimo errore, offline da, dead_letter) come
  `StatoPostinoArchivio` (+ `archiviate`, `guasti_codice`, `guasto_codice`), `RapportoRiconciliazione`,
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
- **Versione** (M3, RISCRITTA dalla terza revisione R1: vedi par. 12): non piu' l'orologio del bot.
- **Scrittore** (A2, M5, M6; R3 della terza revisione): tre unita' indipendenti per lotto (log, denaro, vivo); la voce
  impossibile da salvare per un errore di DATO provato (`errore_di_dato`: surrogato, intero fuori misura, vincolo SQLite)
  va in `scarti_scrittore.jsonl` (fsync) e il resto prosegue; gli errori di I/O si ritentano per sempre; un errore di
  CODICE su tutte le voci non scarta nulla (par. 12); alla chiusura con il disco guasto le voci accettate vanno in `salvataggio-*.jsonl` e
  rientrano all'apertura dopo; `conferma()` e' una soglia contigua; un lavoro sincrono scaduto prima di partire si
  annulla (esito vero: non avvenuto), se e' partito si aspetta il suo esito vero.
- **Postino** (A1, A4, M1, M4): valore non JSON (NaN, Infinity, surrogato) -> dead_letter prima della chiamata; errore di
  dato su tutta la chiamata (\u0000, classe 22) -> bisezione fino alla riga sola; per riga: classe 22 e 23 (tranne 23503)
  -> dead_letter `dato`; classe 42/0A e intestazione `GP001` -> tabella bloccata, segnalata UNA volta, riga in coda;
  tutto il resto -> transitorio, ~6 h di ritenti (360 tentativi, attese fino a 60 s), poi dead_letter `transitorio`.
  **Rientro automatico** delle dead_letter: transitorie ogni 15 min, `dato` e `registro` ogni 24 h (contatore
  `rientri`): una migrazione che corregge un CHECK fa rientrare da sola le righe (PSB 7 n.18); dopo 7 rientri falliti
  una `dato` diventa ARCHIVIATA (par. 12).
  Voce di una tabella non registrata -> dead_letter `registro`. Per chiave: al massimo una voce per chiamata, FIFO
  fra un giro e l'altro (`outbox_pronta`), le voci dopo una chiave fallita aspettano.
- **Log** (A3, M2, B7): riparazione della riga troncata cercando l'ultimo `\n` a blocchi fino all'inizio del file;
  marcatore con la firma della prima riga: oltre la fine del file o file sostituito -> torna a 0 (ritento sicuro con
  `uid`) e si segnala; conteggio della coda incrementale in `stato()`.
- **Manutenzione** (M7, B1): pulizia a pezzi di 1.000 righe (lavori di millisecondi); `auto_vacuum=INCREMENTAL`
  effettivo (VACUUM una tantum) e spazio restituito a pezzi.
- `apri()` puo' sollevare `OSError` (cartella non creabile) o `ArchivioOccupato` (B3): l'aggancio resta su "vecchio".

## 12. Regole della terza revisione (09/10, "PASSA con 4 riserve")

Principio vincolante: **IDENTICO A OGGI**. Oggi vince l'ultima scrittura fatta dal bot e nessuna scrittura viene
scartata; la versione serve SOLO a impedire che una voce VECCHIA della STESSA origine (ritento del postino, rientro da
dead_letter, voce ripetuta dopo un crash) sovrascriva una voce piu' nuova della stessa origine.

- **Versione LOCALE (R1)**. Ogni scrittura (`scrivi`, `accoda`, `transizione`) riceve, nel momento in cui e' accodata e
  sotto lo stesso lucchetto dell'accodamento, la `vseq`: un numero MONOTONO del suo file (`denaro`/`vivo`), persistito in
  `meta.vseq` nella stessa transazione delle righe (mai riusato, nemmeno dopo pulizia e riapertura). Ogni file ha la sua
  `origine` (`processo/regime/id casuale del file`, `meta.origine`): un file ricreato e' un'origine nuova.
  In locale vince SEMPRE l'ultima accodata (fusione delle colonne); `updated_at` del bot si scrive TALE E QUALE (niente
  piu' "+1 us", niente scarti per l'orologio). La colonna `rev_colonna` del registro serve solo alla riconciliazione.
- **Nel cloud** la RPC `postino_consegna(p_tabella, p_op, p_conflitto, p_righe, p_origine, p_versioni)` confronta la
  `vseq` SOLO con le voci della STESSA origine (tabella `public.postino_versioni`: per tabella, chiave, origine la versione
  piu' alta applicata): piu' vecchia -> `vecchia` (riga intatta, evento `dati.riga_vecchia`), uguale -> `ignorata` (era gia'
  applicata: ritento dopo una risposta persa), piu' nuova o origine diversa -> scritta: **fra origini diverse vince
  l'ultima arrivata, come oggi**. La versione registrata e' nella stessa sottotransazione della riga (una riga rifiutata
  non lascia la sua versione); le versioni di oltre 90 giorni le toglie la RPC stessa (100 per chiamata).
- **Rientro delle dead_letter (R2)**: (a) una riga di stato la cui chiave ha gia' una scrittura PIU' NUOVA (vseq piu'
  alta nella riga locale o in outbox) non rientra: resta ARCHIVIATA con la nota "superata" (evento
  `dati.dead_letter_superata`); se la riga locale non c'e' piu', il cloud la scarta comunque come `vecchia` (seconda
  difesa). (b) Una dead_letter di DATO che fallisce `RIENTRI_MAX_DATO` = 7 rientri (uno ogni 24 h) diventa ARCHIVIATA:
  resta su disco, esce dal conteggio d'allarme, non costa piu' chiamate; `stato()` (un `StatoPostinoArchivio`, sottoclasse
  di `StatoPostino` con i campi del contratto invariati) la conta in `archiviate`. Le transitorie (un padre che arriva
  tardi) e quelle di registro rientrano per sempre. (c) `pulisci()` toglie le archiviate dopo
  `CONSERVA_ARCHIVIATE_GIORNI` = 30 giorni dall'archiviazione; mai le attive.
- **Guasto del codice (R3)**: `errore_di_dato` copre SOLO i casi di dato provati (`UnicodeEncodeError`/`DecodeError`,
  `OverflowError`, `sqlite3.IntegrityError`/`DataError`, JSON guasto). Un errore di altro tipo (TypeError,
  ProgrammingError...) che colpisce TUTTE le voci e' un guasto del codice: le voci restano in coda e si ritentano con
  attesa crescente (mai scarti), log CRITICAL al piu' una volta al minuto, contatore `guasti_codice` ed evento d'allarme
  `dati.archivio_guasto_codice`, esposti in `stato()` (`guasti_codice`, `guasto_codice`); se colpisce una voce sola
  mentre le altre passano, la voce va negli scarti. Gli scarti restano nell'allarme 7 giorni (come una `dato` prima
  dell'archiviazione), poi contano fra le archiviate; la pulizia li toglie dopo altri 30 giorni.
- **Disco guasto a processo vivo (R4)**: si ritenta per sempre con attesa crescente (tetto 30 s); il file di salvataggio
  si scrive SOLO alla chiusura. Il chiamante di un lavoro gia' partito (transizione, `accoda`) aspetta l'esito vero.

## 13. Per W1-C1 (porta ordini): semantica di `transizione` e regime delle tabelle della porta

Semantica verificata dal revisore (`transizione.py`) e provata da `test_g1_terza_revisione.py::test_C1_*`:
- riga assente -> `False`; riga con la colonna di stato diversa da `da` (o assente) -> `False`; un secondo claim uguale
  -> `False`; tabella di log -> `ValueError`; tabella non registrata -> `KeyError`;
- cambia UNA colonna sola, `status` (`colonna_stato`); le altre, `updated_at` compreso, restano tali e quali;
- vede tutte le scritture accodate PRIMA (anche non ancora su disco): e' eseguita dal thread di scrittura;
- atomicita' LOCALE: riga e voce di outbox nella stessa transazione, un solo scrittore per archivio. NON e' un lucchetto
  fra processi (due archivi diversi non si vedono): i claim fra processi restano quelli del cloud di oggi;
- durabilita' PIENA (WAL `synchronous=FULL`) solo per le tabelle del regime `stato_denaro`; su `stato_vivo` (NORMAL)
  un claim confermato puo' perdersi a PC spento;
- con il disco guasto il chiamante resta BLOCCATO finche' il disco non torna (mai un esito falso); l'unica eccezione e'
  il lavoro che scade PRIMA di partire: `TimeoutError` "annullato prima di partire (non eseguito)", esito vero.
- Le tabelle della porta (`ordini_ref_visti`, `ordini_seq`) vanno REGISTRATE nel registro con regime `stato_denaro`
  (durabilita' piena: un riferimento d'ordine gia' visto o una sequenza non devono tornare indietro dopo un crash).
