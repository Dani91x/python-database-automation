# REFERTO W1-G2 - Registro delle tabelle, client cloud unico, cache degli algoritmi del cloud (09/10/2026)

Ramo `architettura/w1-g2` da `559a96df`. Comparto G, tappe T2 (con la consegna R23) e T7 del piano. Nessun file
esistente modificato; nessuna rete, nessun DB vero, nessun processo nuovo.

## 1. Cosa ho costruito (e cosa NON fa)

| File | Righe | Punti chiave |
|---|---:|---|
| `Betfair/nucleo/dati/registro.py` | 955 | `_SCRITTURE_DIRETTE` (:149, generato dalla scansione al commit `559a96df`), `SITI_DINAMICI`/`SITI_PASSANTI`/`RPC_DINAMICHE`/`SCRITTURE_REST` (:294-356), `RPC_SCRIVENTI_ELENCO` 72 RPC (:366-450), `_VOCI` 108 tabelle (:483-715), `RegistroTabelle` (:752), `verifica_copertura` (:914), `controlla_coerenza` (:929), `REGISTRO` (:955) |
| `Betfair/nucleo/dati/cloud.py` | 301 | `politica(profilo)` (:80), `costruisci_lettura` (:104), `_Cache` (:140), `ClienteCloud.leggi/rpc/scrivi/rpc_ritentabile/_esegui` (:167-301); `scrivi` rifiuta le tabelle non registrate, `interruttore_client` (:94) |
| `Betfair/nucleo/dati/cache_cloud.py` | 463 | `SorgenteOmega` (:81), `ReplicaEmpirica` (:130: firme di `omega_db`/`mike.db`, `prefetch_lega`, `controlla_ricostruzione`, `avvia`/`ferma`), `lambdas_da_riga` (:295), `DossierPrematch` (:328) |
| `tests/test_g2_registro.py`, `test_g2_cloud.py`, `test_g2_cache_cloud.py` | 407+373+476 | 90 test |
| `Betfair/nucleo/dati/doc/G2_REGISTRO_CLOUD.md` | | schema del `COSA_FA.md` |
| `ARCHITETTURA_2026-10/ondata1/W1-G2/mutazioni_w1g2.py` | | le 17 mutazioni, rifacibili |

**Registro**: 108 voci = le 89 di `00 §0` + le 6 «solo RPC» di `g_copertura_tabelle.py` + 13 trovate dalla scansione
del 09/10 (vedi §9, D2). Ogni voce: chiave naturale, natura, regime, ritardo massimo e proposta di G §4.3 (tutti
dichiarati `STATO_RITARDI = "proposta, da approvare con U-86"`), `rev_colonna` (`updated_at` dove la tabella lo ha
nelle migrazioni), `dipende_da` (REFERENCES delle migrazioni, provato dal test), `scrittori_oggi` (`file:riga` del
codice Python E frontend, siti dinamici e REST risolti a mano, poi `rpc:<nome>`), `scrittore_domani` (04 §6.2).
72 RPC scriventi con le tabelle toccate dalla definizione SQL **chiusa sulle funzioni che chiama** e l'ultima definizione.

**Client**: UN client (`db_client.get_supabase_client`), classificazione (`classifica_guasto_rete`) e motore
(`con_ritentativi`) IMPORTATI. Profili: `bot` = 5/20 s (`usa_timeout_bot`) e attese 0,15/0,30 s; `runner` = 120 s di
libreria come oggi e attese 0,15/0,30 s; `catena` = 120 s e 2-4-8-16-32 s. Si ritenta SOLO: letture, upsert, RPC di
lettura (get_/list_, elenchi di sola lettura) non registrate come scriventi e non in `RPC_NON_IDEMPOTENTI`. Mai insert,
patch, delete, RPC scriventi o sconosciute; mai 4xx, mai 57014 (decide `db_client`). Cache per lettura con `cache_s`
(copie profonde, errori mai in cache, scadenza monotona).

**Cache degli algoritmi (T7)**: `ReplicaEmpirica` serve `get_omega_ht_ft`/`get_omega_minute_ft` dalla memoria con le
firme di `omega_db.ht_ft_transitions`/`minute_transitions` e di `mike.db.ht_ft_rows`; prefetch per lega di 28 chiavi
(1 HT->FT + 18 bucket FT + 9 HT); rilettura completa quando cambia il `built_at` di `omega_ht_ft_transitions`
(pg_cron delle 04:00 UTC), sostituzione in un colpo. Le scadenze di oggi (Omega 6 h, Mike mai: U-53) restano nelle
cache DEI BOT, sopra la replica, intatte. `DossierPrematch`: ponte `live_follow` -> `omega_events` e
`fixture_predictions` a blocchi (3 letture per N eventi), firme di `mike.db`; `build_prematch` resta di Mike.

**Cosa NON fa**: non sostituisce nessuna chiamata di oggi (aggancio = ondata 2); non scrive nel cloud (il postino e'
di W1-G1: `scrivi` e' solo l'estensione che gli serve); non legge `fixtures_for_window`/`market_frequency` (G-036) ne'
le lambda di Safe (E3-026); non porta in locale nessun algoritmo; importarlo non importa `db_client` (provato).

## 2. Contratto

- Implementa `Cloud` (`leggi`, `rpc` con `cache_s`) in `ClienteCloud`; `RegistroTabelle.spec(tabella) -> SpecTabella`
  (G §4.5). `SpecTabella` usata cosi' com'e', con tutti i campi (anche `scrittori_oggi`, `scrittore_domani`).
- **Estensioni proposte (additive, nei miei file)**: `VoceRegistro` (famiglia, proposta CMD-L/L+P/CACHE/CLOUD/BATCH,
  origine, `rpc_scriventi`, `scrittura_fuori_codice`, verifica), `RpcScrivente`, `SitoDinamico`, `Scansione`,
  `EsitoCopertura`; `ClienteCloud.scrivi(tabella, op, righe, on_conflict=, ignora_duplicati=, filtri=)` per il postino
  (ritenta solo l'upsert: un insert con `uid` va mandato come upsert `ignore_duplicates` su `uid`).
- `Natura` del contratto non ha `BATCH` (G la usa): mappata su `STA`/`ARC` + `proposta="BATCH"`.

## 3. Parita'

| Oggi (file:riga) | Nuovo | Test | Esito |
|---|---|---|---|
| `db_client.esegui_con_retry` + `classifica_guasto_rete` (`db_client.py:224-343`) | `ClienteCloud("catena").leggi` | `test_parita_con_db_client_sulla_griglia` (12 risposte: 520 HTML Cloudflare vera, 503 PGRST002, 504 testo, 500 08006, GOAWAY vero, ReadTimeout, ConnectError, 57014, 404 PGRST202, 409 23505, 403 42501, 507 53100) | identici esito, classe e numero di richieste (6 per i transitori, 1 per gli altri) |
| `_exec_retry` del runner (`Betfair/stream/db.py:44`, 3 tentativi 0,15/0,30 s) | profilo `bot`/`runner` | `test_profilo_bot_ritenta_solo_i_transitori` | stesse attese; classificazione di `db_client` (vedi D1) |
| `usa_timeout_bot` (`db_client.py:59`) | `attiva_profilo` | `test_timeout_per_profilo` | client ricreato con lo stesso `httpx.Timeout` 5/20 s; runner `None` |
| `omega_db.ht_ft_transitions` (:1065) / `minute_transitions` (:1078) | `SorgenteOmega.ht_ft/minuti` | `test_sorgente_uguale_a_omega_db_*` (5 leghe x 28 chiavi + lista vuota, null, oggetto, 404, 57014, 520 persistente) | righe e argomenti (corpi delle richieste) identici; [] / None identici |
| RPC (stesse) | `ReplicaEmpirica` | `test_replica_uguale_alla_rpc_per_ogni_lega_e_bucket` | 6 leghe (None, 0, 39, 135, 61) x 28 chiavi uguali riga per riga, 0 richieste nel ciclo |
| `omega_service._empirical_table`/`_minute_table` (:1355, :1324), `dossier.get_empirical` (:141) | gli stessi, con la replica come `db` | `test_bot_identici_con_la_replica_al_posto_della_rpc` | tabelle identiche (`vars()` interi) |
| idem, nel tempo | replica + `controlla_ricostruzione` | `test_rilettura_dopo_la_ricostruzione_delle_04_utc_e_scadenze_di_oggi` | 03:00 prefetch, 04:00 pg_cron, 05:00 rilettura: Omega uguale alla RPC alle 05:00 (notte vecchia, 6 h) e alle 09:01 (notte nuova); Mike resta sulla vecchia con entrambi (mai); controllo negativo: replica senza rilettura DIVERSA dalla RPC |
| `stream/db.get_fixture_prematch_lambdas` (:231) | `lambdas_da_riga` | `test_lambdas_da_riga_uguale_a_*` (12 righe: JSON in stringa, non JSON, zero, negativi, stringhe, None, bool, catena di ripiego; con e senza squadre) | identici |
| `mike.db.fixture_id_for_event/fixture_lambdas/fixture_analysis` (:591-647), `dossier.build_prematch` (:66) | `DossierPrematch` | `test_dossier_uguale_a_mike_db_per_ogni_evento` (11 eventi: solo `live_follow`, solo `omega_events`, entrambe con fixture diverse, fixture non intera, senza riga di previsione, nessuna) | dossier interi identici (`lambda_home/away`, `rho`, `p4_pre`, `p_under35_cal`, fonte calibrata/grezza) |
| tabelle scritte dal codice (`s03_db.analizza_py/ts`, `g_copertura_tabelle.py`) | `verifica_copertura` | `test_il_registro_copre_il_codice_di_oggi` | 0 errori; 3 avvisi dichiarati (`bet_features` vista; due tabelle del pg_cron) |
| `on_conflict` letterali del codice (AST) / REFERENCES delle migrazioni | `chiave_naturale` / `dipende_da` | `test_chiavi_naturali_*`, `test_dipende_da_*` | 39 tabelle con `on_conflict` coincidono; 22 chiavi esterne tutte presenti |
| `Betfair/stream/db.TABELLE_PNL_BETFAIR`, `caricamento.T_*`, mappe di `per_fixture_backfill`/`season_aggregates` | `SITI_DINAMICI` | `test_siti_dinamici_coincidono_con_il_codice` | uguali |

Ingressi veri: il CODICE e le MIGRAZIONI di oggi (scansione completa dei file tracciati), le pagine e i corpi di
errore veri dei run del 08/10. Le righe di `omega_*_transitions` e `fixture_predictions` sono sintetiche con le chiavi
e i tipi delle migrazioni: le vere sono nel cloud (riconciliazione in sola lettura sul PC, §8).

## 4. Migliorie misurate (dichiarate)

- Ciclo di Omega con replica pronta: **0** RPC (oggi 1 RPC sincrona per bucket di 5' senza voce in cache:
  `omega_service.py:1437,1449,1561,1570`). Misura: contatore delle richieste del trasporto nei test.
- Rete che rifiuta tutto dopo il prefetch: replica e dossier rispondono identici con 0 richieste.
- Dossier di Mike per 11 eventi: 3 letture (oggi >= 2 per evento, 3-4 con la fixture).
- Prefetch delle RPC di lettura ritentato sui guasti di rete (oggi un tentativo): un 520 transitorio non perde la tabella.

## 5. Test e falsificazioni

- Miei: **90 verdi** (`test_g2_registro.py` 24, `test_g2_cloud.py` 34, `test_g2_cache_cloud.py` 32), ~25 s.
- Mutazioni sul codice (`mutazioni_w1g2.py`): **17/17 rosse**, ripristino con sha256 identico
  (versione finale: `cloud.py 65fab46a09e6`, `registro.py df97e6d1d8f6`, `cache_cloud.py d09f2c02868f`): ritento di 4xx (M1),
  del 57014 (M2), dell'insert (M3), delle RPC scriventi (M4, M4b), cache senza scadenza (M5), riga del registro tolta
  (M6), sito dinamico non risolto (M7), RPC che scrive una tabella non dichiarata (M8), chiave esterna tolta (M9),
  replica mai riletta dopo `built_at` (M10), errore in cache (M11), `> 0` -> `>= 0` nelle lambda (M12), ordine del
  ponte invertito (M13), memoria senza copia (M14), bucket sbagliati (M15), dossier in memoria dopo un errore (M16).
  Al primo giro M4 e M13 erano VERDI: due buchi dei test, chiusi (RPC "get_" registrata come scrivente; evento in
  entrambe le tabelle con fixture diverse) e rilanciati rossi.
- Falsificazioni interne ai test: 8 tabelle tolte una per una (tra cui una da nome dinamico, una REST, una del
  frontend, la nuova del monitor) -> «TABELLA SCRITTA DAL CODICE E ASSENTE DAL REGISTRO»; RPC tolta; RPC di lettura che
  scrive; file scrittore nuovo; sito dinamico nuovo; REST nuovo; voce senza scrittori dichiarata (avviso) e non
  dichiarata (errore); scrittore sparito (avviso).
- Suite intera (`python -m pytest Betfair/ -q -p no:cacheprovider`, macchina condivisa con 7 agenti):
  giro 1 (commit `93ee4361`) interrotto al 90% SENZA riepilogo (processo terminato dall'esterno, causa non
  accertata: nessun numero utile); giro 2 (commit `cc483f05`): **11.657 verdi, 3 rossi, 87 saltati, 6 xfailed** in
  670 s. Rossi: (a) e (b) `test_g2_registro.py::test_il_registro_copre_il_codice_di_oggi` e
  `::test_voce_che_nessuno_scrive_piu_*`: il registro ha trovato **il mio stesso `cloud.py`** appena tracciato
  (`.table(tabella)` e `.rpc(nome)` dinamici, «NOME DINAMICO NON RISOLTO»): e' il test che fa il suo lavoro.
  Corretto: `ClienteCloud.scrivi` ora RIFIUTA le tabelle non registrate (test nuovo) e i due siti sono dichiarati;
  i miei 90 test rilanciati verdi, mutazioni 17/17 rosse sulla versione finale. (c)
  `Betfair/stream/tests/test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms`
  (28,0 ms > 20 ms): misura di latenza sotto il carico della macchina condivisa, file non mio. Il terzo giro della
  suite non l'ho fatto (tetto di due del brief): da rilanciare al coordinatore.

## 6. Funzionalita' di `01_FUNZIONALITA.md`

Coperte (riuso o parita' provata): G-001, G-002, G-004, G-005, G-006 (attese), G-010, G-024 (parte di Mike), G-026
(RPC), G-033, G-034, G-035, D-018 (Mike), D-019, D-060, K-012. Restano al vecchio codice: G-003, G-007 (client del
tennis), G-008, G-036 (`fixtures_for_window`, `market_frequency`, catena lambda di Omega), E3-026 (Safe), tutte le
scritture G-009..G-032 (postino, T8/T14).

## 7. PSB par. 6/7

Sollecitate: 6.5 (colonne/chiavi vere dalle migrazioni e dal codice), 6.7 (falsificazione: 17 mutazioni), 6.8
(comando e hash qui); par. 7 n. 18 (nessuna eccezione inghiottita: il client rilancia; la sorgente logga con il motivo
e restituisce None come oggi), n. 19 e 37 (cache: errori mai in cache, scadenze intatte, nessuna cache di modulo: la
replica e' un oggetto), n. 21 (registro: `mode` nelle chiavi di ordini/posizioni/regolati), n. 27 (client VERO, corpi
veri), n. 28-30, 35 (test visti rossi). ⊘ con causa «nessun codice di bot, nessun ordine, nessun replay in questa
ondata»: 6.1-6.4, 6.6, 6.9; par. 7 n. 1-17, 20, 22-26, 31-34, 36.

## 8. Aggancio proposto per l'ondata 2

1. **T2, `ARCH_DATI_CLIENT=vecchio|nuovo`** (`cloud.interruttore_client`): nei `main` che oggi chiamano
   `usa_timeout_bot` (`mike/service.py:7764`, `omega/omega_service.py:9156`, `safe_strategy/bot_service.py`,
   `safe_strategy/service.py`) un `ClienteCloud("bot").attiva_profilo()`; `Betfair/stream/db.py:44` e
   `tennis_live/tennis_db.py:66` (`_exec_retry`) in `nuovo` passano da `con_ritentativi` con `ATTESE_BOT_S` SOLO per gli
   upsert (vedi D1). Uguale o meglio: stessi esiti sulla griglia; 0 ritenti di insert/4xx/57014.
2. **T2, riconciliazione in sola lettura sul PC**: per ogni voce con `regime != "cloud"` `count(*)` e hash di chiave
   e `rev_colonna` del giorno prima; per le voci `cloud` `max(updated_at)` (vitalita').
3. **T7, `ARCH_PREFETCH_OMEGA`**: `omega_service.py:1437,1449,1561,1570` passano `replica` invece di `db` in `nuovo`;
   in `ombra` chiamano entrambi e confrontano le righe (reperto se diverse); `replica.richiedi_prefetch(lega)` quando la
   partita entra nel perimetro; `avvia()`/`ferma()` nel ciclo di vita del servizio. **`ARCH_PREFETCH_MIKE`**:
   `mike/service.py:4486,6967` `D.build_prematch(eid, dossier_prematch)` e `:5439` `D.get_empirical(..., replica, ...)`,
   con `ripiego=mike.db` e `precarica` all'avvio e ogni ora. Uguale: righe e dossier identici in ombra per una giornata.
4. **Registro**: il test di copertura entra nella suite (gia' sotto `Betfair/`): una tabella nuova senza voce e' rossa.

## 9. Divergenze per l'utente, rischi, dubbi

- **D1** `net_retry.is_transient` (runner e tennis, `_exec_retry`) ritenta anche il **57014** (il marcatore "timeout"
  prende «canceling statement due to statement timeout») e gli `OSError` WinError 10035/10054/10060 nudi; il client
  nuovo, come chiede il piano, MAI il 57014 e non vede gli OSError nudi (solo quelli avvolti da httpx). Con
  `ARCH_DATI_CLIENT=nuovo` il runner cambierebbe su questi due casi: da decidere (non scelgo io).
- **D2** Tabelle che oggi ricevono righe e NON erano fra le 89+6: `book_odds_cache` e `book_odds_cache_fonte` (RPC
  `refresh_analytics_bets_range` -> `_diag`: lo strumento `g_copertura` non segue le deleghe), `live_market_snapshots`,
  `live_score_timeline`, `tennis_replay_snapshots`, `tennis_replay_punteggio`, `match_lineups`, `match_player_stats`
  (nomi dinamici), `hazard_atlas`, `hazard_atlas_leghe` (REST diretto) e `monitor_metrics` (nuova di T0A, 09/10). Piu'
  le due tabelle del pg_cron lette dagli algoritmi. Tutte registrate.
- **D3** Le 72 RPC: oggi 71 scriventi chiamate da `.rpc()` + `hazard_atlas_salva_versione` (via REST,
  `genera_atlante.py:1103`, invisibile allo strumento). `omega_eventi_chiusi_dall_utente`, `monitor_salute_stato`,
  `monitor_vitalita_raccoglitori` NON scrivono (dichiarate). Rispetto a G §4.3 C la chiusura SQL aggiunge:
  `add_trade_leg` -> anche `personal_trades`; `omega_activate` -> anche `omega_daily_goal`; `omega_request_approve/ignore`
  -> anche `omega_manual_requests`.
- **D4** Correzione a G §3 punto 7: `mike.db.ht_ft_rows` restituisce **None** sull'errore della RPC (lo restituisce gia'
  `omega_db.ht_ft_transitions`); `[]` solo se fallisce l'import. La distinzione non e' persa (parita' provata).
- **D5** Finestra della replica: fra la ricostruzione delle 04:00 e la rilettura di `built_at` (di serie 300 s) la
  replica serve la notte prima mentre la RPC serve la nuova; conta solo se in quella finestra scade una cache del bot.
  Il dossier di Mike si rinfresca ogni ora: `fixture_predictions` aggiornata fra le 02:18 e le 09:43 puo' differire per
  al massimo un'ora. L'ombra lo misura; `built_at` e' letto da `omega_ht_ft_transitions` assumendo che la stessa notte
  ricostruisca anche la tabella per minuto (vero il 08/10: entrambe 04:00:00.17).
- **D6** Mancato prefetch senza ripiego -> None (come un errore di oggi). Per Mike vuol dire 600 s di attesa
  (`_EMPIRICAL_RETRY_S`): in `nuovo` per Mike il ripiego sincrono va tenuto acceso o il prefetch fatto prima.
- **D7** Prudenze da approvare: patch e delete non ritentati (db_client li considera idempotenti); runner a 120 s
  come oggi (G lo critica); l'interruttore «2 guasti di fila» di `db_client` e' di processo, condiviso.
- **D8** `omega_requests`: chi la consuma resta «da chiarire» (G B); registrata `cloud`.
- **Per il coordinatore (integrazione dei rami)**: il test di copertura vede OGNI file tracciato. I moduli nuovi
  degli altri agenti che scrivono nel cloud (es. `postino.py` di W1-G1 con `.table(variabile)`) risulteranno
  «NOME DINAMICO NON RISOLTO» finche' non sono dichiarati in `registro.py` (`SITI_DINAMICI`): e' voluto.
- **Rischio**: il test del registro fissa il numero (108) e l'elenco delle voci in piu': aggiungere una tabella richiede
  di aggiornarlo (voluto). Le righe dei `file:riga` si spostano col codice: AVVISO, non errore; un FILE scrittore nuovo
  e' ERRORE. La scansione legge solo i file tracciati da git (un file nuovo non ancora aggiunto non si vede).

Comandi: `python -m pytest Betfair/nucleo/dati/tests/test_g2_registro.py Betfair/nucleo/dati/tests/test_g2_cloud.py
Betfair/nucleo/dati/tests/test_g2_cache_cloud.py -q -p no:cacheprovider`;
`python ARCHITETTURA_2026-10/ondata1/W1-G2/mutazioni_w1g2.py $(pwd)`. Versioni: supabase 2.28.0, postgrest 2.28.0,
httpx 0.28.1, Python 3.13.
