## 1. Righe per file e per cartella (dai file tracciati)

Script: `s01_righe.py` -> `uscite/s01_righe_per_file.tsv` (una riga per file: percorso, categoria, righe, byte) e
`uscite/s01_riepilogo.txt`. Righe = numero di `\n` (come `wc -l`). Categorie decise dallo script (`s01_righe.py:39-86`):
test = `test_*.py`, `*_test.py`, `conftest.py` o cartella `tests/`; strumenti = cartella `tools/`; script audit = `.py` dentro
`AUDIT_*`, `_AUDIT_*`, `SCHEMI_BOT`, `ARCHITETTURA_2026-10`; **generati** = file che dichiarano «FILE GENERATO»/`@generated` nelle
prime 15 righe (oggi uno solo: `frontend/src/lib/replayBotCatalogo.ts`, dichiarato alle righe 2-9 del file stesso, rigenerato da
`python -m Betfair.stream.backtest.applica_bot --catalogo-ts`).

### 1.1 Totali per categoria e macro-categorie

{{sez:s01_riepilogo.txt:== A. }}
{{sez:s01_riepilogo.txt:== A2.}}

### 1.2 Per cartella di radice (tutte le categorie)

{{sez:s01_riepilogo.txt:== B. }}

### 1.3 `Betfair/` per sottocartella (solo `.py`)

{{sez:s01_riepilogo.txt:== C. }}

### 1.4 I file piu' grandi

{{sez:s01_riepilogo.txt:== D. 25 FILE PIU GRANDI: py_codice_Betfair}}
{{sez:s01_riepilogo.txt:== D. 25 FILE PIU GRANDI: py_codice_radice}}
{{sez:s01_riepilogo.txt:== D. 25 FILE PIU GRANDI: frontend_codice}}

(Le liste dei 25 file piu' grandi di test, test frontend e strumenti sono in `uscite/s01_riepilogo.txt`, sezioni D.)

### 1.5 Il frontend per cartella

{{sez:s01_riepilogo.txt:== F. }}

### 1.6 Cosa contiene la categoria «altro» (1.710.906 righe nel primo giro)

Il primo giro di `s01` metteva in «altro» tutto cio' che non era `.py`, `.sql`, `.md`, frontend o desktop, e contava come righe di
testo anche il PDF (168.866 «righe» del solo `Betfair/Betfair_api_documentation.pdf`, un binario senza NUL nei primi 8 KB) e i `.pkl`.
Corretto: i binari si riconoscono ora anche per estensione (`s01_righe.py:23`). Il blocco vero e' questo (1.542.040 righe, 1.414 file,
+313 file binari a 0 righe):

| Sottocategoria | File | Righe | Cosa sono (fonte: sezione A4 sotto) |
|---|---:|---:|---|
| `altro_dati_json_csv` | 379 | 1.024.505 | JSON pretty-printed: `Betfair/omega/data/hazard_atlas_v2.json` 229.179 + `hazard_atlas_v1.json` 167.313 (gli atlanti di rischio di gol, dati letti dai bot: `Betfair/omega/data/` = 479.424 righe), `AUDIT_2026-09-25` 454.612 (misure e snapshot di plancia), radice 36.058 (`dynamic_cal.json` 26.304 ...), `market_intelligence/cache` 25.009 |
| `altro_html` | 15 | 199.005 | 198.708 sono gli schemi `SCHEMI_BOT/sistema/schemi/*.html` e `ARCHITETTURA_ATTUALE.html` (15.000 righe l'uno circa: SVG incorporati) |
| `altro_txt_log` | 818 | 187.039 | uscite di replay e misure dentro `AUDIT_*` (34.273 in `AUDIT_2026-09-25`), 19.065 righe di `.txt/.log` in radice, 11.398 in `Betfair/` |
| `altro_patch` | 91 | 118.828 | `.patch` dei cantieri, tutti in `AUDIT_*` (53.220 in `AUDIT_2026-10-02`) |
| `altro_script_config` | 111 | 12.663 | `.yml` dei workflow (1.199), `Telegram bot/` (1.790: Edge Functions Deno), `.bat`/`.ps1`, `.mjs` di audit |
| `altro_binari_pdf_img_pkl` | 313 | 0 | png, pdf, pkl, gz (`registrazioni_banco/*.jsonl.gz`) |

Nessuna di queste righe e' codice eseguito dall'app: i JSON di `Betfair/omega/data/` sono dati letti dal codice (atlante hazard),
il resto e' audit, schemi, misure.

{{sez:s01_riepilogo.txt:== A3.}}

### 1.7 Verifica dei numeri di §1 del brief del piano

Esito: 8 confronti su 31 differiscono (nella tabella sotto la colonna «brief» e' il valore del brief, «misurato» quello di `s01`).

{{sez:s01_riepilogo.txt:== E. }}

Spiegazioni (ognuna ricavata dai dati, non ipotizzata):

1. **`Betfair/omega/` 37.500 (brief) contro 20.913 (misurato)**: la differenza e' esattamente 16.587 righe = i `test_*.py` che stanno
   dentro `Betfair/omega/` (non in una cartella `tests/`). Il brief ha contato come «codice» ogni `.py` fuori da cartelle
   `tests/`/`tools/`; con quella definizione si ritrova anche `Betfair/*.py` 7.358 = 6.821 + 537 di test nella radice del pacchetto, e i
   256 file del brief (`s01_righe.py`, riga «RICOSTRUZIONE brief»: 256 file, 186.235 righe).
2. **Backend 271.857 (brief)**: la somma delle componenti dichiarate dal brief (88.987 + 37.500 + 34.635 + 17.755 + 7.358) e'
   **186.235**, non 271.857. Con la stessa definizione del brief si ottengono 186.235 righe in 256 file: il totale dichiarato dal brief
   non e' riproducibile (85.622 righe non spiegate). Con la definizione di questo inventario (solo codice, test separati) il backend
   `Betfair/` + radice e' **193.914** righe in 301 file; con le altre cartelle di radice (`Ai Engine`, `laboratorio`, ...) **219.378**
   righe in 407 file.
3. **Test Python 163.079 (brief) contro 193.411**: non riproducibile (`Betfair/` da solo ha 178.889 righe di test, radice 8.319).
   Verosimile che il brief abbia contato su un albero precedente o con un'altra definizione; non c'e' modo di ricostruirlo dai dati.
4. **Frontend codice 133.686 contro 125.573**: il valore del brief e' compatibile con «tutti i `.ts/.tsx` non di test di `frontend/src`»
   = 134.673 (comprende i 11.099 righe GENERATE di `replayBotCatalogo.ts`); la nostra categoria «codice» esclude il generato
   (125.573) e include i `.css/.js` (con generato 136.672). **Frontend test 73.428 = esattamente i `.test/.spec` `.ts/.tsx`**
   (nostro 73.535 comprende `frontend/src/test/setup.ts` 75 e `forzaSupabaseFinto.ts` 32).
5. **Desktop 1.183 = 1.117 (codice) + 66 (`ambiente_runner.test.js`)**: il brief conta anche il test (la riga «Desktop (js, tutti)» e' UGUALE).
6. **SQL 33.835 = solo `migrations/`**; con `sql/` (886 righe di SQL) e gli altri `.sql` tracciati si arriva a 35.244.
7. Tutti i file nominati nel brief (`omega_service.py` 8.936, `bot_service.py` 11.136, `mike/service.py` 7.551, `replayBotCatalogo.ts` 11.099,
   `useControlRoom.ts` 4.322, ...) e le sottocartelle di `stream/` (scalper 21.620, tennis_live 11.638, tennis_scalper 8.943,
   backtest 13.391, trading 4.301) sono UGUALI.
8. «55 tabelle usate dal codice» (brief) non torna: sono 89 (sezione 3).

