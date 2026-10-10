# G2 - Registro delle tabelle, client cloud unico, cache degli algoritmi del cloud (W1-G2, 09/10/2026)

Schema del `COSA_FA.md` (04 par. 2.4). File: `registro.py`, `cloud.py`, `cache_cloud.py`; test `tests/test_g2_*.py`.
Tappe del piano: T2 (registro + client, consegna R23) e T7 (algoritmi del cloud fuori dal ciclo). Aggiornato dopo la
revisione indipendente (D-1..D-10, referto `ARCHITETTURA_2026-10/ondata1/W1-G2/REFERTO.md` par. 10) e dopo la
seconda (par. 11: Storage delle Edge Function, sentinella mai cieca, memoria potata, cache con generazioni).
Aggiornato il 10/10 per la **decisione 10 dell'utente** ("tutta l'app in tempo reale per Betfair; il cloud solo come
backup; il resto sul DB locale"): i dati CALCOLATI dal cloud arrivano appena il cloud ricalcola (par. 1, `Sorveglianza`;
referto par. 12; migrazione `migrations/nucleo_sentinella_cloud_2026-10-10.sql`, da applicare dall'utente).

## 1. Scopo

- **`registro.py`**: UNA voce `SpecTabella` per ogni tabella del cloud che oggi riceve righe (121: le 89 di
  `00_INVENTARIO.md` par. 0, le 6 scritte solo da RPC, 26 trovate dalla scansione), con chi la scrive OGGI
  (`file:riga`, `rpc:<nome>`, o la funzione SQL/pg_cron dichiarata) e chi DOMANI, chiave naturale, natura, regime e
  ritardo massimo (G par. 4.3, "proposta, da approvare con U-86"), `rev_colonna`, `dipende_da`, `schema_nel_repo`.
  Piu' le 74 RPC scriventi con le tabelle che toccano, i bucket dello Storage e le eccezioni DML motivate. E' lo
  strumento dell'ordine dell'utente "il cloud non perde nessun dato": un test rifiuta ogni tabella scritta dal codice,
  dai workflow o da una funzione SQL/pg_cron e assente dal registro.
- **`cloud.py`**: `ClienteCloud`, implementazione del protocollo `Cloud`: UN client (quello di `db_client`),
  timeout per profilo (`bot`, `runner`, `catena`), ritento SOLO dell'idempotente (letture, RPC di lettura, upsert
  sulla chiave naturale o su `uid` ignorando i duplicati), cache per lettura invalidata dalle scritture (anche
  tutte le RPC in cache), con generazioni contro le letture in volo e potatura periodica delle voci scadute.
- **`cache_cloud.py`**: `ReplicaEmpirica` (tabelle HT->FT e per minuto di Omega/Mike servite dalla memoria,
  prefetch per lega, rilettura a ogni giro del pg_cron vista da `omega_transitions_state`, generazioni contro le gare
  fra thread, chiavi mancanti richieste di nuovo) e `DossierPrematch` (ponte evento->fixture e `fixture_predictions`
  letti prima dell'aggancio di Mike; solo i positivi, per 300 s, potati a ogni `precarica`). Sentinella illeggibile =
  "non so": dopo 3 errori di fila si rilegge comunque (mai ciechi a una ricostruzione).
- **`cache_cloud.py`, decisione 10** (`SentinellaCloud`, `Sorveglianza`): UNA chiamata ogni 5 s alla RPC
  `nucleo_sentinella_cloud` (impronta di Omega + per ogni evento seguito: fixture del ponte, riga presente,
  `nucleo_versione` scritta dal trigger) e al cambio di un'impronta si rilegge SOLO quel pezzo: l'evento cambiato
  (`DossierPrematch.applica_impronte`, poi `prendi_cambiati` per Mike) o le tabelle di Omega (`notifica_sentinella` al
  thread della replica, `sentinella_esterna=True`). Senza la migrazione: le letture REST di oggi ogni 15 s, la RPC
  riprovata ogni 10 minuti. Con la versione del trigger una voce del dossier confermata a ogni giro resta fresca
  (rinnovo); senza, scade a 300 s come prima. La lettura diretta di riserva (`ripiego` = `mike.db`) e il ritento di
  Mike ogni 300 s restano accesi: mai piu' lento di oggi.

## 2. Entrate

- `registro`: nessuna a runtime (dati dichiarativi). Il test lo confronta con una `Scansione` del codice, dei workflow
  e delle migrazioni.
- `cloud`: tabella + filtri (`select`, `order`, `limit`, colonna -> eq/in/is null, `col__gte` ecc.), RPC + argomenti.
- `cache_cloud`: un `Cloud`; leghe da preparare (`prefetch_lega`, `richiedi_prefetch`, `drena_coda`); eventi (`precarica`);
  eventi da sorvegliare (`DossierPrematch.segui`, all'aggancio i `tracked` di Mike a ogni giro).

## 3. Uscite

- `REGISTRO.spec(tabella) -> SpecTabella`; `verifica_copertura(registro, scansione) -> EsitoCopertura(errori, avvisi)`.
- `ClienteCloud.leggi/rpc` (contratto) e `scrivi` (estensione per il postino, SOLO tabelle del registro): righe in
  copia profonda; errori: l'eccezione originale (4xx, 57014, applicativi) o `db_client.GuastoRete` dopo l'ultimo tentativo.
- `ReplicaEmpirica.ht_ft_transitions/minute_transitions/ht_ft_rows` e `DossierPrematch.fixture_id_for_event/
  fixture_lambdas/fixture_analysis/ht_ft_rows`: STESSE firme e STESSI ritorni delle funzioni di oggi
  (`omega_db`, `mike.db`), compresi "[] = vuota, None = errore, mai in cache".
- `Sorveglianza.giro() -> EsitoGiro(modo, omega_notificata, cambiati, errore)`; `DossierPrematch.prendi_cambiati()`:
  gli eventi il cui dossier e' cambiato nel cloud, gia' riletti (Mike all'aggancio li riprova subito se ciechi).

## 4. Dipendenze ammesse

`contratto.py` del comparto; `db_client` (importato alla prima chiamata, MAI all'import: il suo `config` legge
`.env`); stdlib. Nessun bot importato: le funzioni dei bot sono gli ARBITRI solo nei test. Il test del registro
importa gli strumenti dell'inventario (`s03_db.py`, `g_copertura_tabelle.py`) senza copiarli.

## 5. Funzionalita' coperte (id di `01_FUNZIONALITA.md`) e test che le prova

| Id | Cosa | Test |
|---|---|---|
| G-001, K-012 | client per thread di `db_client` riusato (anche il rinnovo dopo GOAWAY) | `test_g2_cloud.py::test_transitorio_poi_successo_e_client_nuovo_dopo_goaway` |
| G-002, D-060 | profilo bot 5/20 s; runner e catena a 120 s come oggi | `test_timeout_per_profilo` |
| G-004 | classificazione dei guasti identica (griglia di 12 risposte) | `test_parita_con_db_client_sulla_griglia` |
| G-005 | `con_ritentativi` riusato; mai insert/patch/delete/upsert senza chiave/RPC scriventi, mai 4xx, mai 57014 | `test_profilo_bot_ritenta_solo_i_transitori`, `test_insert_di_log_mai_ritentata`, `test_upsert_ritentato_solo_sulla_chiave_naturale`, `test_57014_e_4xx_mai_ritentati_neanche_negli_upsert`, `test_rpc_di_lettura_ritentate_scriventi_mai` |
| G-006 | attese 0,15/0,30 s del runner di oggi (`_exec_retry`) nei profili bot e runner | `test_profilo_bot_ritenta_solo_i_transitori` |
| G-010 | lambda pre-match dalla riga di `fixture_predictions` | `test_g2_cache_cloud.py::test_lambdas_da_riga_uguale_a_get_fixture_prematch_lambdas` |
| G-024, G-033, D-018 | ponte evento->fixture, lambda, analisi; `build_prematch` identico; la fixture tardiva accende il modello | `test_dossier_uguale_a_mike_db_per_ogni_evento`, `test_dossier_la_fixture_che_arriva_dopo_accende_il_modello`, `test_dossier_errore_su_live_follow_*`, `test_dossier_errori_mai_in_memoria_e_scadenza` |
| G-026, G-034, G-035, D-019 | RPC HT->FT e per minuto; cache di Omega (6 h) e di Mike (mai) intatte sopra la replica | `test_sorgente_uguale_a_omega_db_*`, `test_replica_*`, `test_bot_identici_*`, `test_rilettura_*`, `test_ricostruzione_della_sola_tabella_per_minuto`, `test_gara_*`, `test_chiave_mancante_*` |
| decisione 10 (G-033, G-034, G-035) | dossier cambiato o comparso nel cloud entro 5 s (15 s senza migrazione), MAI dopo il ritento di 300 s di oggi (Mike vero, orologio finto, 15 istanti x 3 scenari x 2 modi + sorveglianza guasta); Omega vista in 5 s; una chiamata per giro; gare e errori | `test_g2_sorveglianza.py` (45), `test_g2_pg_sentinella.py` (7, PostgreSQL usa-e-getta: trigger, RPC, permessi, impronta identica alle letture REST, finto = vero, giro completo) |
| (R23, G par. 4.3) | registro tabella per tabella + test di copertura (codice Python e TUTTI i .ts/.js, workflow, migrazioni, Storage) + golden | `test_g2_registro.py` (38 test) |

Restano al codice di oggi: G-003 (rinnovo preventivo della catena), G-007 (client parallelo del tennis), G-008,
G-036 (`fixtures_for_window`, `market_frequency`), E3-026 (lambda di Safe per nome), tutte le scritture (postino: W1-G1).

## 6. Interruttore previsto (ondata 2)

`ARCH_DATI_CLIENT=vecchio|nuovo` per processo (`cloud.interruttore_client()`); `ARCH_PREFETCH_<BOT>=vecchio|ombra|nuovo`
(in ombra la replica risponde e si CONFRONTA con la RPC, che si chiama ancora). Di serie: `vecchio`. La sorveglianza
(decisione 10) nasce con il prefetch del processo (`ARCH_PREFETCH_<BOT>` diverso da `vecchio`); la migrazione
`nucleo_sentinella_cloud_2026-10-10.sql` e' additiva e la applica l'utente: senza, tutto funziona con le letture REST.

## 7. Come si sostituisce

Cambiare cloud (altro Postgres/PostgREST): solo `cloud.py` (+ i suoi test sul trasporto finto). Una tabella nuova:
una riga `_v(...)` in `registro.py` (il test di copertura lo pretende, anche per una tabella scritta da una funzione
SQL o da un workflow). Un algoritmo nuovo del cloud: una `Sorgente*` + una replica con le firme della funzione di oggi
e il suo test di parita'.

## 8. Come si prova da solo

`python -m pytest Betfair/nucleo/dati/tests/test_g2_registro.py Betfair/nucleo/dati/tests/test_g2_cloud.py Betfair/nucleo/dati/tests/test_g2_cache_cloud.py Betfair/nucleo/dati/tests/test_g2_sorveglianza.py Betfair/nucleo/dati/tests/test_g2_pg_sentinella.py -q -p no:cacheprovider`
(189 test, ~40 s; il registro scansiona tutti i file tracciati; i 7 del PostgreSQL vero solo con
`G2_PG_PSQL="-h <socket> -p <porta> -U postgres"` su un PostgreSQL usa-e-getta, script in referto par. 12). Nessuna rete:
client supabase VERO su `httpx.MockTransport`. Mutazioni: `python ARCHITETTURA_2026-10/ondata1/W1-G2/mutazioni_w1g2.py $(pwd)`
(85: 41 + 15 del revisore + 29 della decisione 10, di cui 7 sulla migrazione solo con `G2_PG_PSQL`; tutte rosse;
`MUTAZIONI_FILTRO=D10` per le sole nuove).

## 9. Misure

- Ciclo di decisione di Omega con la replica pronta: 0 richieste (oggi una RPC sincrona per ogni bucket di 5'
  senza voce in cache) - `test_replica_uguale_alla_rpc_per_ogni_lega_e_bucket`, `test_rete_che_rifiuta_tutto_*`.
- Dossier di Mike per 11 eventi: 3 letture a blocchi contro >= 2 letture a evento oggi (lette dal test).
- Prefetch per lega: 28 RPC (1 HT->FT + 18 bucket FT + 9 bucket HT), fuori dal ciclo; sentinella: 3 letture di una riga.
- Decisione 10 (contate al trasporto, `test_carico_dichiarato_richieste_al_minuto`): con la RPC **12 richieste al minuto**
  per processo (replica + dossier, fino a 500 eventi); senza la migrazione 24/min fino a 50 eventi, 36/min con 60.
  Latenza dal ricalcolo del cloud alla memoria pronta: <= 5 s + 1 RPC + la rilettura del solo evento (2-3 letture);
  con le letture di U-60 (p50 111 / p90 148 / p99 493 ms) ~5,5 s al p90, media ~3 s; oggi 0-300 s (media 150 s).
  Costo della RPC sul PostgreSQL 16 usa-e-getta: 0,86 ms a chiamata con 60 eventi; trigger +25 us a riga riscritta
  (`ARCHITETTURA_2026-10/ondata1/W1-G2/misure_d10.txt`).

## 10. `PROCESSO_STANDARD_BOT.md` par. 6/7

Sollecitate: 6.5 (colonne e chiavi vere delle migrazioni nel registro, test golden), 6.7 (falsificazione: 56
mutazioni), 6.8 (referto); par. 7 n. 18 (scrittura fallita mai warning: il client non inghiotte), n. 19/37 (cache:
errori e negativi mai in cache, scadenze intatte), n. 27 (finti con chiavi e tipi veri: client vero, corpi veri di
PostgREST), n. 29/30/35 (mutazioni rosse). Il resto e' ⊘ (nessun codice di bot, nessun ordine): dettaglio nel
referto.
