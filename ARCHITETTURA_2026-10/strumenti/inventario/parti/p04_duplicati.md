## 4. Duplicazioni

Script: `s04_duplicati.py` (funzioni con lo stesso nome in file diversi, confronto con `difflib` sul testo normalizzato: via commenti,
righe vuote, docstring; classi IDENTICHE = testo uguale, QUASI = rapporto >= 0.90, DIVERSE < 0.90; `uscite/s04_*`), `s06_top30_duplicati.py`
(le 30 piu' pesanti, `uscite/s06_top_duplicati.{txt,tsv}`), `s09_gemelli_file.py` (file quasi-copia, `uscite/s09_gemelli_file.{txt,tsv}`).
Per leggere i numeri: **il confronto per NOME misura le funzioni omonime, non la logica ripetuta con nomi diversi**; i file «gemelli» (4.3)
completano il quadro. Altri strumenti gia' nel repo da non rifare: `strumenti/dati_g1/gemelle.py` -> `dati_g1/uscite/gemelle.tsv` (stessa-nome nei
moduli DB), `strumenti/h_gemelli_adattatori.py` (adattatori di replay per bot), `strumenti/e5_gemelli*.py`, `strumenti/D_gemelle_servizi.py`.

### 4.1 Funzioni con >= 3 copie in produzione

{{sez:s04_riepilogo.txt:nomi di funzione con}}
{{sez:s04_riepilogo.txt:== nome | copie}}
{{sez:s04_riepilogo.txt:== i 4 nomi del brief}}

Il brief del piano (§1) scrive «`read_book` definita 17 volte, `process_market_book` 15, `_now_iso` 17, `log` 18». Misurato in produzione: `read_book`
**3** (file 3; altre 26 nei test), `process_market_book` **20** (20 file), `_now_iso` **17** (17 file, **identiche**: 34 righe in tutto), `log` **7**
(7 file; 96 con test e audit). Le 17 copie di `_now_iso` stanno nei 6 moduli DB (`mike/db.py:52`, `omega_db.py:432`, `bot_db.py:55`, `safe_strategy/db.py:16`, `stream/db.py:40`, `tennis_db.py:79`), in 5 worker
(`order_worker.py:32`, `refresh_worker.py:31`, `live_order_worker.py:650`, `risk_engine_worker.py:43`, `xhedge_worker.py:23`) e in 6 altri file di servizio/scores (`s04_dettaglio_copie.tsv`).
`process_market_book` (20 copie, 1.826 righe) e' il metodo di aggancio che `flumine` impone a ogni `Strategy`: le copie sono 19 gruppi diversi,
quindi **non e' una duplicazione da eliminare**; l'unica coppia quasi-uguale ha 211 righe recuperabili (`s06_top_duplicati.txt`).

### 4.2 Le 30 piu' pesanti per righe totali (esclusi i metodi omonimi generici `main`, `__init__`, `run`, ...)

Colonne: `ident` = copie identiche al capogruppo, `quasi` = copie con rapporto 0.90-0.99, `div` = copie diverse (da sole), `recup` = righe delle
copie non capogruppo di gruppi con >= 2 membri (stima per difetto: una copia condivisa basterebbe).

{{sez:s06_top_duplicati.txt:== TOP 30}}
{{sez:s06_top_duplicati.txt:== omonimie}}

Giudizio: **299 dei 319 nomi con >= 3 copie sono DIVERSI** (stesso nome, corpi diversi: strategie e adattatori per bot); solo 20 nomi hanno
copie identiche o quasi-identiche:

| Nome | Copie | Righe | Giudizio | Dove (prime 3 copie, `s04_dettaglio_copie.tsv`) |
|---|---:|---:|---|---|
| `_now_iso` | 17 | 34 | IDENTICHE | `Betfair/stream/db.py:40`, `Betfair/mike/db.py:52`, `Betfair/omega/omega_db.py:432` ... |
| `per_codice` | 6 | 30 | IDENTICHE | (6 file) |
| `_try_enter` | 3 | 503 | QUASI (0.92-1.00) | `Betfair/stream/scalper/scalper_bot.py:1183`, `Betfair/stream/tennis_scalper/tennis_scalper_bot.py:1256`, `laboratorio/scalper_lab/scalper_bot_base.py:815` |
| `_update_flow` | 3 | 117 | IDENTICHE | `scalper_bot.py:1688`, `tennis_scalper_bot.py:1692`, `scalper_bot_base.py:1209` |
| `_enter_join` | 3 | 215 | QUASI | `scalper_bot.py:1378`, `tennis_scalper_bot.py:1462`, `scalper_bot_base.py:1024` |
| `_flatten` | 3 | 110 | QUASI | `scalper_bot.py:2661`, `tennis_scalper_bot.py:2322`, `scalper_bot_base.py:1655` |
| `_manage_maker` | 3 | 431 | QUASI/DIVERSA (163/157/111 righe) | `scalper_bot.py:1524`, `tennis_scalper_bot.py:1534`, `scalper_bot_base.py:1097` |
| `_matched_position`, `_handle_cancelling`, `_enter_maker` | 3+3+3 | 85+51+101 | QUASI | stesso trio |
| `compute_green`, `micro_price`, `wom_imbalance`, `_long_drift_signed`, `_long_drift`, `_recent_move`, `_flow_sums`, `_line_key`, `_now`, `_tempi_on` | 3 ciascuna | 27-69 | IDENTICHE | stesso trio |
| `enqueue_live_order` | 3 | 15 | IDENTICHE | i 3 moduli DB `bot_db.py`, `omega_db.py`, `mike/db.py` |

### 4.3 File quasi-copia (stesso nome di funzione, corpo uguale o quasi)

{{file:s09_gemelli_file.txt}}

Letture:

1. **Lo scalper calcio e lo scalper tennis sono lo stesso programma per un quarto del codice**: 20 funzioni identiche e 7 quasi-identiche su 49 in comune
   (806 righe di `scalper_bot.py`, 24,3%); in piu' esiste un terzo file, `laboratorio/scalper_lab/scalper_bot_base.py` (2.076 righe, nella cartella
   `laboratorio/` classificata ARCHIVIO in 7), che e' una copia di lavoro del bot di produzione: 22 funzioni identiche a `scalper_bot.py` e 23 a
   `tennis_scalper_bot.py`. Il resto (22 funzioni «diverse» nel confronto calcio/tennis) sono le regole di strategia (soglie, gambe, uscite): vanno lasciate invariate.
2. **I moduli DB dei bot NON sono copie riga per riga.** `bot_db.py`/`omega_db.py` condividono 28 nomi di funzione ma solo 2 sono identiche e 3 quasi
   (29 righe, 2,8%); `bot_db`/`mike/db` 26 nomi, 3 identiche (8 righe); `omega_db`/`mike/db` 22 nomi, 2 identiche. Il brief parla di «5 moduli diversi, uno per bot»:
   e' vero (in 3.1), ma la ripetizione e' di FORMA (stessi nomi `get_trade`, `get_event`, `get_live_order_request`, `get_live_order_mirror`, `enqueue_live_order`,
   `read_control`, `runner_heartbeat`, `live_follow_status` in 3 moduli) piu' che di testo. Dove sono davvero uguali sono funzioni minuscole
   (`_sb` 2 righe in 3 moduli, `_now_iso` 2 righe in 5, `enqueue_live_order` 15 righe in 3). L'unico duplicato grande per testo nel livello DB e'
   `_exec_retry` (`Betfair/stream/db.py:44` 15 righe e `Betfair/stream/tennis_live/tennis_db.py:63` 14 righe, similarita' 0,96: `dati_g1/uscite/gemelle.tsv`).
3. **Conseguenza per il piano**: la riduzione di righe «per fusione» e' reale per i bot scalper (circa 800 righe di funzioni identiche +
   la copia di laboratorio) e per i cinque servizi (nella forma, non nel testo); sul livello DB va misurata con un'altra tecnica (generazione delle
   funzioni di accesso dalle tabelle), non con il confronto di testo.

### 4.4 File identici

`s04_duplicati.py` raggruppa per hash i file tracciati con contenuto identico (>= 30 righe): **35 gruppi**, `uscite/s04_file_identici.txt`.
**Nessun gruppo contiene codice di produzione** (`grep Betfair/` e `*.py` nel file: 0). 24 gruppi sono coppie `frontend/src/fotografia/snapshot/*.off.json` /
`*.v2.json` (le fotografie dell'interfaccia vecchia e del «guscio v2», identiche per costruzione: `frontend/src/fotografia/`); i restanti 11 sono copie in
`AUDIT_*` (es. `AUDIT_2026-09-29/in_attesa_del_via/MIKE_P5_5.md` = `AUDIT_2026-09-30/MIKE_P5_5.md`) e le due copie dei test e2e
`frontend/e2e_fase1/{clientVero.ts,percorsi.e2e.test.tsx}` = `AUDIT_2026-09-25/e2e_fase1/strumenti/` (124 e 1.129 righe).

