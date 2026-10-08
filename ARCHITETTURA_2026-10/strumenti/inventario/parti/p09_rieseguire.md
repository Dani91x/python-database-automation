## 9. Come rieseguire (ogni numero di questo documento)

Tutti gli script stanno in `ARCHITETTURA_2026-10/strumenti/inventario/`, usano solo la libreria standard e `git` in sola lettura, NON importano codice di produzione, NON caricano `.env`,
scrivono SOLO in `strumenti/inventario/uscite/` (nessun file > 1 MB: il piu' grande, `s01_righe_per_file.tsv`, ~350 KB). Interprete: `.venv/Scripts/python.exe` (Python di progetto), dalla radice del repo
o da qualunque cartella (`_comune.py` risale da solo alla radice). Ordine (le dipendenze vanno da sinistra a destra); durate misurate su questo PC l'08/10/2026:

| Ordine | Script | Produce | Sezione | Durata |
|---:|---|---|---|---|
| 1 | `s01_righe.py` | `s01_righe_per_file.tsv`, `s01_riepilogo.txt` | 1, 0 | ~11 s |
| 2 | `s02_import.py` | `s02_moduli.tsv`, `s02_archi.tsv`, `s02_esterni.tsv`, `s02_morti.txt`, `s02_riepilogo.txt` | 2 | ~25 s |
| 3 | `s03_db.py` | `s03_*.tsv`, `s03_riepilogo.txt` | 3 | ~35 s |
| 4 | `s04_duplicati.py` | `s04_*` | 4 | ~40 s |
| 5 | `s05_tabelle_stringa.py` | `s05_tabelle_stringa.tsv` | 3 | ~10 s |
| 6 | `s06_top30_duplicati.py` | `s06_top_duplicati.{txt,tsv}` | 4 | <1 s |
| 7 | `s07_cartelle_import.py` | `s07_cartelle.txt`, `s07_archi_cartelle.tsv` | 2 | <1 s |
| 8 | `s08_morti_verifica.py` | `s08_morti_verifica.{txt,tsv}` | 2 | ~5 s |
| 9 | `s09_gemelli_file.py` | `s09_gemelli_file.{txt,tsv}` | 4 | <1 s |
| 10 | `k01_radice.py` | `k01_radice.tsv` | 7 | ~3 min (scorre il disco) |
| 11 | `k02_grafo_import.py` | `k02_moduli.tsv`, `k02_import_dinamici.txt` | 2 | ~40 s |
| 12 | `k03_classifica_radice.py` | `k03_*` | 7 | ~4 s |
| 13 | `p01_porte.py` | `p01_porte.tsv`, `p01_porte_riepilogo.txt` | 5 | ~5 s |
| 14 | `f01_frontend.py` | `f01_*` | 6 | ~2 s |
| 15 | `c01_confronto_02_10.py` | `c01_*` | 8 | ~11 s |
| 16 | `g01_tabelle_md.py` | `g01_tabelle_db.md`, `g01_rpc.md` | 3 | <1 s |
| 17 | `z_assembla.py` | `ARCHITETTURA_2026-10/00_INVENTARIO.md` (da `parti/*.md` + le uscite) | tutte | <1 s |

Comando tipo: `.venv/Scripts/python.exe ARCHITETTURA_2026-10/strumenti/inventario/s01_righe.py`. `z_assembla.py` e' l'unico che scrive fuori da `uscite/` (scrive il documento);
i segnaposto `sez` e `file` (doppia graffa, vedi la docstring di `z_assembla.py`) dentro `parti/` sono sostituiti con le uscite, il testo a mano resta quello delle parti (i numeri scritti a mano nel testo NON si aggiornano da soli: vanno riletti se il repo cambia).
Il numero di file e di righe dipende da `HEAD`: questo documento e' fotografato a `dfae4541`; con file non committati o con un altro `HEAD` i numeri cambiano (`s01` stampa `HEAD` e lo stato di `git status` in testa).

Script del primo giro riusati/corretti: `s01` (aggiunte categorie, binari per estensione, generati, sezioni A2-A4 e F, ricostruzione del brief), `s02` (alias `ai_engine`, chiave canonica degli importatori), `k02` (BOM),
`k01`, `s03`, `s04` invariati. Script mancanti aggiunti: `s05`-`s09`, `k03`, `p01`, `f01`, `c01`, `g01`, `z_assembla`. Altre misure nella cartella `strumenti/` (non mie): `misure/m*.py` (feed, DB, risorse), `dati_g1/`, `dati_J/`, `h_*`, `e*_gemelli*`.

