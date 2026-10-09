# G2 - Registro delle tabelle, client cloud unico, cache degli algoritmi del cloud (W1-G2, 09/10/2026)

Schema del `COSA_FA.md` (04 par. 2.4). File: `registro.py`, `cloud.py`, `cache_cloud.py`; test `tests/test_g2_*.py`.
Tappe del piano: T2 (registro + client, consegna R23) e T7 (algoritmi del cloud fuori dal ciclo).

## 1. Scopo

- **`registro.py`**: UNA voce `SpecTabella` per ogni tabella del cloud che oggi riceve righe (108: le 89 di
  `00_INVENTARIO.md` par. 0, le 6 scritte solo da RPC, 13 trovate dalla scansione), con chi la scrive OGGI
  (`file:riga`, `rpc:<nome>`) e chi DOMANI, chiave naturale, natura, regime e ritardo massimo (G par. 4.3,
  "proposta, da approvare con U-86"), `rev_colonna`, `dipende_da` (chiavi esterne delle migrazioni).
  Piu' le 72 RPC scriventi con le tabelle che toccano. E' lo strumento dell'ordine dell'utente "il cloud non
  perde nessun dato": un test rifiuta ogni tabella scritta dal codice e assente dal registro.
- **`cloud.py`**: `ClienteCloud`, implementazione del protocollo `Cloud`: UN client (quello di `db_client`),
  timeout per profilo (`bot`, `runner`, `catena`), ritento SOLO dell'idempotente, cache per lettura.
- **`cache_cloud.py`**: `ReplicaEmpirica` (tabelle HT->FT e per minuto di Omega/Mike servite dalla memoria,
  prefetch per lega, rilettura dopo il `built_at` del pg_cron delle 04:00 UTC) e `DossierPrematch` (ponte
  evento->fixture e `fixture_predictions` letti prima dell'aggancio di Mike).

## 2. Entrate

- `registro`: nessuna a runtime (dati dichiarativi). Il test lo confronta con una `Scansione` del codice.
- `cloud`: tabella + filtri (`select`, `order`, `limit`, colonna -> eq/in/is null, `col__gte` ecc.), RPC + argomenti.
- `cache_cloud`: un `Cloud`; leghe da preparare (`prefetch_lega`, `richiedi_prefetch`); eventi (`precarica`).

## 3. Uscite

- `REGISTRO.spec(tabella) -> SpecTabella`; `verifica_copertura(registro, scansione) -> EsitoCopertura(errori, avvisi)`.
- `ClienteCloud.leggi/rpc` (contratto) e `scrivi` (estensione per il postino): righe in copia profonda; errori:
  l'eccezione originale (4xx, 57014, applicativi) o `db_client.GuastoRete` dopo l'ultimo tentativo.
- `ReplicaEmpirica.ht_ft_transitions/minute_transitions/ht_ft_rows` e `DossierPrematch.fixture_id_for_event/
  fixture_lambdas/fixture_analysis/ht_ft_rows`: STESSE firme e STESSI ritorni delle funzioni di oggi
  (`omega_db`, `mike.db`), compresi "[] = vuota, None = errore, mai in cache".

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
| G-005 | `con_ritentativi` riusato; mai insert/patch/delete/RPC scriventi, mai 4xx, mai 57014 | `test_profilo_bot_ritenta_solo_i_transitori`, `test_insert_di_log_mai_ritentata`, `test_57014_e_4xx_mai_ritentati_neanche_negli_upsert`, `test_rpc_di_lettura_ritentate_scriventi_mai` |
| G-006 | attese 0,15/0,30 s del runner di oggi (`_exec_retry`) nei profili bot e runner | `test_profilo_bot_ritenta_solo_i_transitori` |
| G-010 | lambda pre-match dalla riga di `fixture_predictions` | `test_g2_cache_cloud.py::test_lambdas_da_riga_uguale_a_get_fixture_prematch_lambdas` |
| G-024, G-033, D-018 | ponte evento->fixture, lambda, analisi; `build_prematch` identico | `test_dossier_uguale_a_mike_db_per_ogni_evento`, `test_dossier_errori_mai_in_memoria_e_scadenza_oraria` |
| G-026, G-034, G-035, D-019 | RPC HT->FT e per minuto; cache di Omega (6 h) e di Mike (mai) intatte sopra la replica | `test_sorgente_uguale_a_omega_db_*`, `test_replica_uguale_alla_rpc_per_ogni_lega_e_bucket`, `test_bot_identici_con_la_replica_al_posto_della_rpc`, `test_rilettura_dopo_la_ricostruzione_delle_04_utc_e_scadenze_di_oggi` |
| (R23, G par. 4.3) | registro tabella per tabella + test di copertura | `test_g2_registro.py` (24 test) |

Restano al codice di oggi: G-003 (rinnovo preventivo della catena), G-007 (client parallelo del tennis), G-008,
G-036 (`fixtures_for_window`, `market_frequency`), E3-026 (lambda di Safe per nome), tutte le scritture (postino: W1-G1).

## 6. Interruttore previsto (ondata 2)

`ARCH_DATI_CLIENT=vecchio|nuovo` per processo (`cloud.interruttore_client()`); `ARCH_PREFETCH_<BOT>=vecchio|ombra|nuovo`
(in ombra la replica risponde e si CONFRONTA con la RPC, che si chiama ancora). Di serie: `vecchio`.

## 7. Come si sostituisce

Cambiare cloud (altro Postgres/PostgREST): solo `cloud.py` (+ i suoi test sul trasporto finto). Una tabella nuova:
una riga `_v(...)` in `registro.py` (il test di copertura lo pretende). Un algoritmo nuovo del cloud: una
`Sorgente*` + una replica con le firme della funzione di oggi e il suo test di parita'.

## 8. Come si prova da solo

`python -m pytest Betfair/nucleo/dati/tests/test_g2_registro.py Betfair/nucleo/dati/tests/test_g2_cloud.py Betfair/nucleo/dati/tests/test_g2_cache_cloud.py -q -p no:cacheprovider`
(89 test, ~25 s; il registro scansiona tutti i file tracciati). Nessuna rete: client supabase VERO su `httpx.MockTransport`.

## 9. Misure

- Ciclo di decisione di Omega con la replica pronta: 0 richieste (oggi una RPC sincrona per ogni bucket di 5'
  senza voce in cache) - `test_replica_uguale_alla_rpc_per_ogni_lega_e_bucket`, `test_rete_che_rifiuta_tutto_*`.
- Dossier di Mike per 10 eventi: 3 letture a blocchi contro >= 2 letture a evento oggi (lette dal test).
- Prefetch per lega: 28 RPC (1 HT->FT + 18 bucket FT + 9 bucket HT), fuori dal ciclo.

## 10. `PROCESSO_STANDARD_BOT.md` par. 6/7

Sollecitate: 6.5 (colonne vere delle migrazioni nel registro; chiavi naturali = `on_conflict` del codice),
6.7 (falsificazione), 6.8 (referto); par. 7 n. 18 (scrittura fallita mai warning: il client non inghiotte),
n. 19/37 (cache: errori mai in cache, scadenze intatte), n. 27 (finti con chiavi e tipi veri: client vero,
corpi veri di PostgREST), n. 29/30/35 (mutazioni rosse, vedi referto). Il resto e' ⊘ (nessun codice di bot,
nessun ordine): dettaglio nel referto `ARCHITETTURA_2026-10/ondata1/W1-G2/REFERTO.md`.
