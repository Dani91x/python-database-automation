# REFERTO W1-G2 - Registro delle tabelle, client cloud unico, cache degli algoritmi del cloud (09/10/2026)

Ramo `architettura/w1-g2` da `559a96df`. Comparto G, tappe T2 (con la consegna R23) e T7 del piano. Nessun file
esistente modificato; nessuna rete, nessun DB vero, nessun processo nuovo. Consegna 1: `c10099d4`; revisione
indipendente «DA CORREGGERE» (D-1..D-10); consegna 2: `7fe2b64a` + `2089d977`; seconda revisione «DA CORREGGERE (lieve)»; consegna 3 (questa):
`d21dadb4` + referto (par. 11). Le correzioni sono
elencate al par. 10; i paragrafi 1-9 descrivono lo stato DOPO le correzioni.

## 1. Cosa ho costruito (e cosa NON fa)

| File | Righe | Punti chiave |
|---|---:|---|
| `Betfair/nucleo/dati/registro.py` | 1085 | `ECCEZIONI_DML` (:69), `_SCRITTURE_DIRETTE` (generato dalla scansione al commit `559a96df`), `SITI_DINAMICI`/`SITI_PASSANTI`/`RPC_DINAMICHE`/`SCRITTURE_REST`/`SITI_STORAGE` (:393), `RPC_SCRIVENTI_ELENCO` 74 RPC (:414), `SENZA_SCHEMA_NEL_REPO` (:524), `_VOCI` 121 tabelle (:550), `RegistroTabelle`, `_controlla_migrazioni` (:1020), `verifica_copertura` (:1041), `controlla_coerenza`, `REGISTRO` (:1085) |
| `Betfair/nucleo/dati/cloud.py` | 333 | `politica(profilo)`, `costruisci_lettura`/`applica_filtri`, `_Cache` (con `svuota_tabella`), `ClienteCloud.leggi/rpc/scrivi/upsert_ritentabile/rpc_ritentabile/_esegui`, `interruttore_client` |
| `Betfair/nucleo/dati/cache_cloud.py` | 535 | `SorgenteOmega` (RPC + `sentinella`), `ReplicaEmpirica` (generazioni, fusione, `prefetch_lega(solo_mancanti=)`, `richiedi_prefetch`, `drena_coda`, `richiedi_incomplete`, `controlla_ricostruzione`, `avvia`/`ferma`), `lambdas_da_riga`, `DossierPrematch` (solo positivi, 300 s) |
| `tests/test_g2_registro.py`, `test_g2_cloud.py`, `test_g2_cache_cloud.py` | 689+451+747 | 130 test |
| `Betfair/nucleo/dati/doc/G2_REGISTRO_CLOUD.md` | | schema del `COSA_FA.md` |
| `ARCHITETTURA_2026-10/ondata1/W1-G2/mutazioni_w1g2.py` | | le 56 mutazioni (41 mie + 15 del revisore), rifacibili |

**Registro**: 121 voci = le 89 di `00 §0` + le 6 «solo RPC» di `g_copertura_tabelle.py` + 26 trovate dalla scansione
(13 alla consegna 1, 13 con la revisione: par. 10, D-1). Ogni voce: chiave naturale, natura, regime, ritardo massimo e
proposta di G §4.3 (dichiarati `STATO_RITARDI = "proposta, da approvare con U-86"`), `rev_colonna` (`updated_at` dove
la colonna esiste nelle migrazioni: test golden), `dipende_da` (REFERENCES delle migrazioni), `scrittori_oggi`
(`file:riga` del codice Python, frontend e workflow, siti dinamici e REST risolti a mano, poi `rpc:<nome>`),
`scrittore_domani` (04 §6.2), `schema_nel_repo` (19 tabelle hanno il CREATE TABLE fuori dal repo: la loro chiave non e'
verificabile ed e' marcata come tale). 74 RPC scriventi con le tabelle toccate dalla definizione SQL **chiusa sulle
funzioni che chiama**. Il test di copertura guarda: `.table/.rpc` del Python e del frontend, i workflow
`.github/**/*.yml` (REST `rpc/<nome>` e tabelle con POST/PATCH/DELETE), il REST diretto, lo Storage, e il DML
(INSERT/UPDATE/DELETE/TRUNCATE) di OGNI funzione delle migrazioni e di ogni `cron.schedule`; i nomi che non sono tabelle
del cloud sono eccezioni con motivo (`ECCEZIONI_DML`: parole SQL, `pg_temp`, temporanee, schema di backup).

**Client**: UN client (`db_client.get_supabase_client`), classificazione (`classifica_guasto_rete`) e motore
(`con_ritentativi`) IMPORTATI. Profili: `bot` = 5/20 s (`usa_timeout_bot`) e attese 0,15/0,30 s; `runner` = 120 s di
libreria come oggi e attese 0,15/0,30 s; `catena` = 120 s e 2-4-8-16-32 s. Si ritenta SOLO: letture, RPC di lettura
(get_/list_, elenchi di sola lettura) non registrate come scriventi e non in `RPC_NON_IDEMPOTENTI`, e gli upsert che
arbitrano sulla chiave naturale del registro (o su `uid` ignorando i duplicati: log dopo U-50). Mai insert, patch,
delete, upsert senza chiave (= insert), RPC scriventi o sconosciute; mai 4xx, mai 57014 (decide `db_client`). `scrivi`
rifiuta le tabelle non registrate e invalida la cache di lettura della tabella. Cache per lettura con `cache_s`.

**Cache degli algoritmi (T7)**: `ReplicaEmpirica` serve `get_omega_ht_ft`/`get_omega_minute_ft` dalla memoria con le
firme di `omega_db.ht_ft_transitions`/`minute_transitions` e di `mike.db.ht_ft_rows`; prefetch per lega di 28 chiavi
(1 HT->FT + 18 bucket FT + 9 HT); sentinella = `omega_transitions_state` (updated_at/published_at, cambia a ogni giro
del pg_cron anche quando cambia solo la tabella per minuto) + `built_at` massimo HT->FT + `omega_build_jobs`; al cambio
si apre una generazione nuova, si rilegge e si FONDE (le voci rimaste vecchie escono); le scritture di una generazione
superata si scartano; le chiavi mancanti si richiedono di nuovo (al piu' ogni 60 s per lega). Le scadenze di oggi
(Omega 6 h, Mike mai: U-53) restano nelle cache DEI BOT, sopra la replica, intatte. `DossierPrematch`: ponte
`live_follow` -> `omega_events` e `fixture_predictions` a blocchi (3 letture per N eventi), firme di `mike.db`; in
memoria SOLO i positivi e per 300 s (= `mike/service._DOSSIER_RETRY_SEC`); `build_prematch` resta di Mike.

**Cosa NON fa**: non sostituisce nessuna chiamata di oggi (aggancio = ondata 2); non scrive nel cloud (il postino e'
di W1-G1: `scrivi` e' solo l'estensione che gli serve); non legge `fixtures_for_window`/`market_frequency` (G-036) ne'
le lambda di Safe (E3-026); non porta in locale nessun algoritmo; importarlo non importa `db_client` (provato).

## 2. Contratto

- Implementa `Cloud` (`leggi`, `rpc` con `cache_s`) in `ClienteCloud`; `RegistroTabelle.spec(tabella) -> SpecTabella`
  (G §4.5). `SpecTabella` usata cosi' com'e', con tutti i campi.
- **Estensioni proposte (additive, nei miei file)**: `VoceRegistro` (famiglia, proposta CMD-L/L+P/CACHE/CLOUD/BATCH,
  origine, `rpc_scriventi`, `scrittura_fuori_codice`, verifica, `schema_nel_repo`), `RpcScrivente`, `SitoDinamico`,
  `Scansione` (con `dml_migrazioni`, `storage`), `EsitoCopertura`; `ClienteCloud.scrivi(tabella, op, righe,
  on_conflict=, ignora_duplicati=, filtri=)` e `upsert_ritentabile` per il postino (un log con `uid` va mandato come
  upsert `on_conflict="uid"`, `ignora_duplicati=True`).
- `Natura` del contratto non ha `BATCH` (G la usa): mappata su `STA`/`ARC` + `proposta="BATCH"`.

## 3. Parita'

| Oggi (file:riga) | Nuovo | Test | Esito |
|---|---|---|---|
| `db_client.esegui_con_retry` + `classifica_guasto_rete` (`db_client.py:224-343`) | `ClienteCloud("catena").leggi` | `test_parita_con_db_client_sulla_griglia` (12 risposte: 520 HTML Cloudflare vera, 503 PGRST002, 504 testo, 500 08006, GOAWAY vero, ReadTimeout, ConnectError, 57014, 404 PGRST202, 409 23505, 403 42501, 507 53100) | identici esito, classe e numero di richieste |
| `_exec_retry` del runner (`Betfair/stream/db.py:44`, 3 tentativi 0,15/0,30 s) | profilo `bot`/`runner` | `test_profilo_bot_ritenta_solo_i_transitori` | stesse attese; classificazione di `db_client` (vedi D1 al par. 9) |
| `usa_timeout_bot` (`db_client.py:59`) | `attiva_profilo` | `test_timeout_per_profilo` | stesso `httpx.Timeout` 5/20 s; runner `None` |
| `omega_db.ht_ft_transitions` (:1065) / `minute_transitions` (:1078) | `SorgenteOmega.ht_ft/minuti` | `test_sorgente_uguale_a_omega_db_*` | righe, argomenti, [] / None identici |
| RPC (stesse) | `ReplicaEmpirica` | `test_replica_uguale_alla_rpc_per_ogni_lega_e_bucket` | 6 leghe x 28 chiavi uguali riga per riga, 0 richieste nel ciclo |
| `omega_service._empirical_table`/`_minute_table` (:1355, :1324), `dossier.get_empirical` (:141) | gli stessi, con la replica come `db` | `test_bot_identici_con_la_replica_al_posto_della_rpc` | tabelle identiche |
| idem, nel tempo | replica + sentinella | `test_rilettura_dopo_la_ricostruzione_delle_04_utc_e_scadenze_di_oggi`, `test_ricostruzione_della_sola_tabella_per_minuto` | Omega uguale alla RPC alle 05:00 e alle 09:01, Mike sulla notte vecchia con entrambi; ricostruzione dei soli minuti vista |
| idem, con un altro thread nel mezzo | generazioni + fusione | `test_gara_rilettura_e_prefetch_fonde_non_sostituisce`, `test_gara_ripiego_lento_non_scrive_la_notte_vecchia` | lega preparata durante la rilettura conservata; righe della notte vecchia scartate |
| `stream/db.get_fixture_prematch_lambdas` (:231) | `lambdas_da_riga` | `test_lambdas_da_riga_uguale_a_*` (12 righe) | identici |
| `mike.db.fixture_id_for_event/fixture_lambdas/fixture_analysis`, `dossier.build_prematch` | `DossierPrematch` | `test_dossier_uguale_a_mike_db_per_ogni_evento`, `test_dossier_la_fixture_che_arriva_dopo_accende_il_modello`, `test_dossier_errore_su_live_follow_*` | dossier interi identici; la fixture/previsione che arriva dopo accende il modello al primo ritento, come oggi |
| codice, workflow, migrazioni (`s03_db`, `g_copertura_tabelle.py`, corpi `$$` e `cron.schedule`) | `verifica_copertura` | `test_il_registro_copre_il_codice_di_oggi` | 0 errori; 1 avviso dichiarato (`bet_features` vista) + RPC dormiente |
| `on_conflict` del codice (AST), PK/UNIQUE/indici unici e REFERENCES delle migrazioni, colonna `updated_at` | `chiave_naturale`, `dipende_da`, `rev_colonna`, `schema_nel_repo` | `test_chiavi_naturali_*`, `test_golden_*`, `test_dipende_da_*`, `test_schema_nel_repo_*` | coincidono; (regime, ritardo, coalesce, chiave) di G §4.3 fissati da una tabella golden |

Ingressi veri: il CODICE, i WORKFLOW e le MIGRAZIONI di oggi (scansione completa dei file tracciati), le pagine e i
corpi di errore veri dei run del 08/10. Le righe di `omega_*_transitions` e `fixture_predictions` sono sintetiche con
le chiavi e i tipi delle migrazioni: le vere sono nel cloud (riconciliazione in sola lettura sul PC, par. 8).

## 4. Migliorie misurate (dichiarate)

- Ciclo di Omega con replica pronta: **0** RPC (oggi 1 RPC sincrona per bucket di 5' senza voce in cache:
  `omega_service.py:1437,1449,1561,1570`). Misura: contatore delle richieste del trasporto nei test.
- Rete che rifiuta tutto dopo il prefetch: replica e dossier (positivi) rispondono identici con 0 richieste.
- Dossier di Mike per 11 eventi: 3 letture (oggi >= 2 per evento, 3-4 con la fixture); i negativi restano al ripiego.
- Prefetch delle RPC di lettura ritentato sui guasti di rete (oggi un tentativo).

## 5. Test e falsificazioni

- Miei: **130 verdi** (`test_g2_registro.py` 38, `test_g2_cloud.py` 45, `test_g2_cache_cloud.py` 47), ~45 s
  (consegna 2: 118). Mutazioni della consegna 3: par. 11.
- Mutazioni sul codice (`mutazioni_w1g2.py`): **35/35 rosse**, ripristino con sha256 identico (`cloud.py 6879b6b05f59`,
  `registro.py 7aac8b4f7401`, `cache_cloud.py a334cec6bf61`). M1-M16 della consegna 1 (riadattate al codice nuovo) e
  M17-M32 della revisione: negativi del dossier in memoria (M17), scadenza 3600 s e 36000 s (M18, M18b: quella del
  revisore), upsert senza `on_conflict` o su colonne qualsiasi ritentato (M19, M19b), chiave mancante mai richiesta
  (M20), sentinella solo su HT->FT (M21), rilettura che sostituisce (M22), scrittura di una generazione vecchia
  (M23), cache non invalidata (M24), filtri di patch/delete solo eq/in (M25), `refresh_analytics_riepilogo` dichiarata
  di sola lettura (M26: quella del revisore), `lanci_action` tolta (M27), sito Storage tolto (M28), `rev_colonna` tolto
  (M29, la K), ritardo cambiato (M30, la L), chiave ridotta (M31), schema dichiarato a torto (M32).
  Al primo giro M16 era VERDE (nessun test con `live_follow` illeggibile): chiuso con
  `test_dossier_errore_su_live_follow_nessun_evento_in_memoria` e rilanciato rosso.
- Falsificazioni interne ai test: 8 tabelle del codice e 5 scritte da funzioni SQL tolte una per una; RPC tolta; RPC
  di lettura che scrive; file scrittore nuovo; sito dinamico, REST e Storage nuovi; DML di un cron non registrato;
  voce senza scrittori dichiarata (avviso) e non dichiarata (errore); scrittore sparito (avviso).
- Suite intera (`python -m pytest Betfair/ -q -p no:cacheprovider`, macchina condivisa):
  - consegna 2, commit `7fe2b64a` (una volta, come chiesto dal coordinatore): **11.689 verdi, 0 rossi, 87 saltati,
    6 xfailed** in 387 s;
  - consegna 1: giro 1 interrotto al 90% senza riepilogo (causa esterna non accertata); giro 2 (`cc483f05`) 11.657
    verdi e 3 rossi: due erano il registro che trovava il mio stesso `cloud.py` (corretto: `scrivi` rifiuta le
    tabelle non registrate, siti dichiarati), uno la misura di latenza
    `test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms` (28 ms, carico della macchina;
    verde nel giro della consegna 2).

## 6. Funzionalita' di `01_FUNZIONALITA.md`

Coperte (riuso o parita' provata): G-001, G-002, G-004, G-005, G-006 (attese), G-010, G-024 (parte di Mike), G-026
(RPC), G-033, G-034, G-035, D-018 (Mike), D-019, D-060, K-012. Restano al vecchio codice: G-003, G-007 (client del
tennis), G-008, G-036 (`fixtures_for_window`, `market_frequency`, catena lambda di Omega), E3-026 (Safe), tutte le
scritture G-009..G-032 (postino, T8/T14).

## 7. PSB par. 6/7

Sollecitate: 6.5 (colonne/chiavi vere dalle migrazioni e dal codice), 6.7 (falsificazione: 35 mutazioni), 6.8
(comando e hash qui); par. 7 n. 18 (nessuna eccezione inghiottita), n. 19 e 37 (cache: errori e negativi mai in
cache, scadenze intatte, nessuna cache di modulo), n. 21 (`mode` nelle chiavi di ordini/posizioni/regolati), n. 27
(client VERO, corpi veri), n. 28-30, 35 (test visti rossi, anche quelli scoperti dal revisore). ⊘ con causa «nessun
codice di bot, nessun ordine, nessun replay in questa ondata»: 6.1-6.4, 6.6, 6.9; par. 7 n. 1-17, 20, 22-26, 31-34, 36.

## 8. Aggancio proposto per l'ondata 2

1. **T2, `ARCH_DATI_CLIENT=vecchio|nuovo`** (`cloud.interruttore_client`): nei `main` che oggi chiamano
   `usa_timeout_bot` (`mike/service.py:7764`, `omega/omega_service.py:9156`, `safe_strategy/bot_service.py`,
   `safe_strategy/service.py`) un `ClienteCloud("bot").attiva_profilo()`; `Betfair/stream/db.py:44` e
   `tennis_live/tennis_db.py:66` (`_exec_retry`) in `nuovo` passano da `con_ritentativi` con `ATTESE_BOT_S` SOLO per gli
   upsert sulla chiave naturale (vedi D1). Uguale o meglio: stessi esiti sulla griglia; 0 ritenti di insert/4xx/57014.
2. **T2, riconciliazione in sola lettura sul PC**: per ogni voce con `regime != "cloud"` `count(*)` e hash di chiave
   e `rev_colonna` del giorno prima; per le voci `cloud` `max(updated_at)` (vitalita').
3. **T7, `ARCH_PREFETCH_OMEGA`**: `omega_service.py:1437,1449,1561,1570` passano `replica` invece di `db` in `nuovo`;
   in `ombra` chiamano entrambi e confrontano le righe; `replica.richiedi_prefetch(lega)` quando la partita entra nel
   perimetro; `avvia()`/`ferma()` nel ciclo di vita del servizio. **`ARCH_PREFETCH_MIKE`**: `mike/service.py:4486,6967`
   `D.build_prematch(eid, dossier_prematch)` e `:5439` `D.get_empirical(..., replica, ...)`, con `ripiego=mike.db` e
   `precarica` all'avvio e almeno ogni 300 s per le partite seguite. Uguale: righe e dossier identici in ombra.
4. **Registro**: il test di copertura e' gia' nella suite (`Betfair/`): una tabella nuova senza voce e' rossa.

## 9. Divergenze per l'utente, rischi, dubbi

- **D1** `net_retry.is_transient` (runner e tennis, `_exec_retry`) ritenta anche il **57014** e gli `OSError` WinError
  nudi; il client nuovo, come chiede il piano, MAI il 57014 e non vede gli OSError nudi (solo quelli avvolti da httpx).
  Con `ARCH_DATI_CLIENT=nuovo` il runner cambierebbe su questi due casi: da decidere (non scelgo io).
- **D2** Tabelle che oggi ricevono righe e NON erano fra le 89+6: 26 (elenco nel test
  `test_le_89_dell_inventario_e_le_6_da_rpc_sono_registrate`), fra cui `book_odds_cache(_fonte)` (RPC delegata), le
  6 dei nomi dinamici, `hazard_atlas(_leghe)` (REST), `monitor_metrics` (T0A), i 3 `analytics_riepilogo_*` (RPC
  notturna dei workflow), `analytics_prob_staging` (dormiente), 8 tabelle del pg_cron e delle funzioni SQL di Omega e `lanci_action`.
- **D3** Le RPC scriventi sono 74: 71 chiamate da `.rpc()`, `hazard_atlas_salva_versione` (REST, `genera_atlante.py:1103`),
  `refresh_analytics_riepilogo` (curl, `predictions_results_backfill.yml:200`), `flush_analytics_prob_staging`
  (nessun chiamante). Rispetto a G §4.3 C la chiusura SQL aggiunge `add_trade_leg` -> `personal_trades`,
  `omega_activate` -> `omega_daily_goal`, `omega_request_approve/ignore` -> `omega_manual_requests`.
- **D4** Correzione a G §3 punto 7: `mike.db.ht_ft_rows` restituisce **None** sull'errore della RPC; la distinzione
  non e' persa (parita' provata).
- **D5 (comportamento osservabile di Omega in «nuovo», revisione D-5)**: fra un giro del pg_cron e la rilettura della
  sentinella (di serie 300 s) e durante la rilettura stessa la replica serve le righe precedenti mentre la RPC serve le
  nuove; conta solo se in quella finestra scade una cache di Omega (6 h). La sentinella ora vede anche la
  ricostruzione dei SOLI minuti (`omega_transitions_state`); NON vede una modifica fatta a mano alle tabelle senza
  passare dalle funzioni del pg_cron o da `omega_build_jobs`. L'ombra la misura.
- **D6 (comportamento osservabile di Mike in «nuovo», revisione D-2)**: il dossier positivo vale 300 s: se
  `fixture_predictions` cambia una riga GIA' con gol attesi (es. `db_json_analisi` riscritto fra le 02:18 e le 09:43)
  Mike puo' vedere per al massimo 300 s il valore precedente; i negativi vanno sempre al ripiego (= oggi). Un mancato
  prefetch senza ripiego risponde None: per Mike vuol dire 600 s di attesa (`_EMPIRICAL_RETRY_S`), quindi per Mike il
  ripiego sincrono va tenuto acceso.
- **D7** Prudenze da approvare: patch e delete non ritentati; nei processi delle action (`DB_RESILIENZA_ACTION=1`) il
  TRASPORTO di `db_client` ritenta da se' PATCH/DELETE (e gli upsert): li' il "un tentativo" di `scrivi` non vale;
  runner a 120 s come oggi; l'interruttore «2 guasti di fila» di `db_client` e' di processo, condiviso.
- **D9 (seconda revisione) script batch e ritento in «nuovo»**: con `ARCH_DATI_CLIENT=nuovo` gli upsert SENZA
  `on_conflict` non si ritentano (sono equivalenti a un INSERT per il client): `generate_dynamic_cal.py:459` e
  `load_poisson_calibration_to_db.py:65` (`poisson_calibration`) avrebbero UN tentativo, salvo il trasporto di
  `db_client` acceso con `DB_RESILIENZA_ACTION=1` nei processi delle action (che li ritenta da se'). Verificato di
  persona: `build_direzione.py:226` ha `on_conflict=pk` con `pk = "engine,market,selection,league_id,prob_bucket"`
  (:219) = chiave naturale del registro, quindi QUELLO si ritenterebbe. Oggi nessuno dei tre passa dal client nuovo
  (sono raccoglitori, invariati): conta solo se un domani li si aggancia.
- **D8** `omega_requests`: chi la consuma resta «da chiarire» (G B). `analytics_prob_staging`/`flush_analytics_prob_staging`:
  dormienti nel repo (registrate, avviso).
- **Per il coordinatore (integrazione dei rami)**: il test di copertura vede OGNI file tracciato. I moduli nuovi
  degli altri agenti che scrivono nel cloud (es. `postino.py` di W1-G1 con `.table(variabile)`) o le loro migrazioni
  con funzioni che scrivono risulteranno ERRORI finche' non sono dichiarati in `registro.py`: e' voluto.
- **Rischio**: il test del registro fissa il numero (121) e l'elenco delle voci in piu' (voluto). Le righe dei
  `file:riga` si spostano col codice: AVVISO; un FILE scrittore nuovo e' ERRORE. La scansione legge solo i file
  tracciati da git. Il DML delle funzioni e' trovato con espressioni regolari (non un parser SQL): un `EXECUTE format(...)`
  dinamico non si vede.

## 10. Correzioni dopo la revisione (09/10, revisore indipendente su `c10099d4`)

| Rilievo | Correzione | Prova (test; mutazione) |
|---|---|---|
| D-1 GRAVE registro incompleto | scansione estesa a `.github/**/*.yml` (RPC e REST), DML di OGNI funzione e `cron.schedule` delle migrazioni con `ECCEZIONI_DML` motivate, Storage (`SITI_STORAGE`, bucket `ai-models-league-<id>`); registrate `analytics_riepilogo_segnali/decisioni/meta` (RPC `refresh_analytics_riepilogo`), `analytics_prob_staging` (+ RPC `flush_analytics_prob_staging`), `omega_ht_ft_transitions_raw`, `omega_minute_transitions_raw`, `omega_transitions_league_counts/_ledger/_runs/_state`, `omega_minute_league_counts`, `omega_build_jobs`, `lanci_action`; anche i siti REST dinamici di lettura dichiarati | `test_workflow_*`, `test_falsifica_rpc_dei_workflow_dichiarata_di_sola_lettura`, `test_falsifica_tabella_scritta_da_funzioni_sql_tolta` (5), `test_eccezioni_dml_*`, `test_storage_*`; M26 (quella del revisore), M27, M28 |
| D-2 ALTO negativi del dossier per 1 h | solo positivi in memoria (evento con fixture, riga con gol attesi), `SCADENZA_DOSSIER_S = 300` = `_DOSSIER_RETRY_SEC` | `test_dossier_la_fixture_che_arriva_dopo_accende_il_modello`, `test_dossier_scadenza_uguale_al_ritento_di_mike`; M17, M18, M18b |
| D-3 upsert senza `on_conflict` ritentato | `upsert_ritentabile`: solo `on_conflict` == chiave naturale del registro, o `uid` + ignora duplicati | `test_upsert_ritentato_solo_sulla_chiave_naturale` (7 casi); M19, M19b |
| D-4 chiave mancante mai riletta | il mancato richiede la lega (al piu' ogni 60 s), `prefetch_lega(solo_mancanti=True)`, `richiedi_incomplete` nel giro | `test_chiave_mancante_di_una_lega_nota_si_riprefetcha`; M20 |
| D-5 sentinella su una sola tabella | `sentinella()` = `omega_transitions_state` + `built_at` HT->FT + `omega_build_jobs` | `test_ricostruzione_della_sola_tabella_per_minuto`; M21 |
| D-6 gara rilettura/prefetch | generazioni: scritture di una generazione superata scartate; rilettura che FONDE e poi toglie le voci vecchie | `test_gara_*` (2); M22, M23 |
| D-7/D-8 filtri, cache, trasporto delle action | `applica_filtri` unico (operatori, None, frozenset) anche per patch/delete; `svuota_tabella` dopo `scrivi`; nota su `DB_RESILIENZA_ACTION` (docstring e D7) | `test_filtri_di_patch_e_delete_e_cache_invalidata`; M24, M25 |
| D-9 carattere non ASCII | tolto (tutti i miei file ASCII, controllato) | `grep -P '[^\x00-\x7F]'` = 0 |
| D-10 e mutazioni K/L | `schema_nel_repo` + `SENZA_SCHEMA_NEL_REPO` (19); golden `rev_colonna` (colonna `updated_at` nelle migrazioni), chiave = PK/UNIQUE/indice unico vero, (regime, ritardo, coalesce, chiave) di G §4.3 | `test_schema_nel_repo_*`, `test_golden_*` (3); M29 (K), M30 (L), M31, M32 |

Portate all'utente come divergenze: D-2 e D-5 (par. 9, D5 e D6).

## 11. Seconda revisione (09/10, su `7fe2b64a`/`2089d977`; commit `d21dadb4`)

sha256 dopo le correzioni: `cloud.py 4a2780107806`, `registro.py 5baf19f2a476`, `cache_cloud.py a1524645a447`.
Mutazioni (`mutazioni_w1g2.py`): **56/56 rosse** = 41 mie (M1-M38) + 15 del revisore (`REV A1`..`REV D4`, riprese tali e
quali dal suo `mie_mutazioni.py`), ogni file ripristinato con sha256 identico. Il suo script, rilanciato sulla
versione nuova: 15/15 rosse (prima 8/15: B1, B4, C2, C3, C4, D2, D3 sopravvivevano).

| Punto | Correzione (file:riga) | Test | Mutazione rossa |
|---|---|---|---|
| 1 Storage mancante | `registro.py:405` `SITI_STORAGE` con `make-daily-post/index.ts` bucket `Loghi` (:253 upload, :263 URL); la scansione guarda TUTTI i `.ts/.tsx/.js/.mjs/.cjs` tracciati esclusi `node_modules`, `dist`, `build` e i file `.test./.spec.` (`test_g2_registro.py:102` `_analizza_ts`, :117 `_chiamate_ts_altrove`); il `.from(<bucket>)` dello Storage non e' piu' scambiato per una tabella | `test_storage_delle_edge_function_scansionato_e_falsificato` (:537): senza la dichiarazione e' rosso | M33 |
| 2 B1, B4 ritardo del ri-prefetch | invariato (`cache_cloud.py:61`, 60 s): mancava il test | `test_ritardo_del_riprefetch_e_di_60_secondi` (`test_g2_cache_cloud.py:641`, 59 s nessuna richiesta, 60 s richiesta, scritti letterali) | REV B1, REV B4 (e REV B2) |
| 2 C2, C3, C4 sentinella | invariata (`cache_cloud.py:121-123`); il finto ora ha righe di disturbo in tutte e tre le tabelle (stato `id=2`, versioni piu' vecchie) e rispetta `id=eq.1` e `order` | `test_sentinella_vede_ogni_sua_lettura` (:671, 3 casi: solo HT->FT, solo `omega_build_jobs`, solo `published_at`) | REV C2, C3, C4 (e C1) |
| 2 D2 prefetch con la generazione catturata | invariato (`cache_cloud.py:195-208`, `gen` catturata all'inizio): mancava il test | `test_gara_prefetch_scrive_con_la_generazione_catturata_all_inizio` (:684) | REV D2 |
| 2 D3 rilettura toglie le voci vecchie | invariato (`cache_cloud.py:292`): mancava il test | `test_rilettura_toglie_le_voci_vecchie_non_rilette` (:701) | REV D3 |
| 3 memoria del dossier | `DossierPrematch.pota()` (`cache_cloud.py:456`), chiamata da `precarica` | `test_dossier_la_memoria_non_cresce_oltre_la_finestra` (:737: 40 precarica ogni 100 s, mai piu' di 3 eventi, nessuna voce oltre 300 s) | M34 |
| 4 sentinella che fallisce | scelta: lettura fallita = "non so"; dopo `SENTINELLA_ERRORI_MAX = 3` errori di fila (`cache_cloud.py:64`, ~15 min con l'intervallo di serie) rilettura FORZATA e sentinella "ignota", cosi' la prima lettura riuscita rilegge ancora (`controlla_ricostruzione`, :253) | `test_sentinella_illeggibile_non_rende_ciechi` (:715) | M35 |
| 5 RPC in cache dopo `scrivi` | `_Cache.svuota_tabella` (`cloud.py:201`) svuota anche TUTTE le RPC in cache (una RPC di lettura puo' leggere qualunque tabella: il registro conosce solo le tabelle delle RPC che scrivono) | `test_rpc_in_cache_svuotate_dopo_una_scrittura` (`test_g2_cloud.py:314`) | M36 |
| 5 lettura in volo | generazione per gruppo (`t:<tabella>`, `r`) catturata prima della richiesta (`cloud.py:264`, :283); `metti` rifiuta se cambiata (:184) | `test_lettura_in_volo_non_rimette_in_cache_il_vecchio` (:326) | M37 |
| 5 potatura della cache | ogni `POTA_OGNI = 64` inserimenti (`cloud.py:157`) | `test_cache_pota_le_voci_scadute_ogni_tanto` (:342) | M38 |
| 6 referto | questo paragrafo; divergenza D9 al par. 9 | - | - |

Test miei: 130 verdi. Suite intera (una volta, su `d21dadb4`): **11.701 verdi, 0 rossi, 87 saltati, 6 xfailed** in 597 s.

Comandi: `python -m pytest Betfair/nucleo/dati/tests/test_g2_registro.py Betfair/nucleo/dati/tests/test_g2_cloud.py
Betfair/nucleo/dati/tests/test_g2_cache_cloud.py -q -p no:cacheprovider`;
`python ARCHITETTURA_2026-10/ondata1/W1-G2/mutazioni_w1g2.py $(pwd)`. Versioni: supabase 2.28.0, postgrest 2.28.0,
httpx 0.28.1, Python 3.13.
