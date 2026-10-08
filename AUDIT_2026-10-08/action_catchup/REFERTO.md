# Action «Seasons Catchup (buchi di dati)»: resilienza di rete (08/10/2026, delegato Opus)

Ordine dell'utente: «Risolvi DEFINITIVAMENTE i problemi della GitHub Action "Seasons Catchup
(buchi di dati)" che continua a fallire tutti i giorni.»

Ore dall'orologio del PC: inizio 14:55, fine 15:34 (08/10/2026). Ramo `claude/eloquent-franklin-g2nyk5`.

## 1. Classificazione dei fallimenti (log veri, `gh run view <id> --log-failed`)

Ultime 29 run: 8 rosse (non 7: c'e' anche la 37185437609 del 04/10 mattina).

| Run | Istante (UTC) | Passo | Errore (dal log) | Classe |
|---|---|---|---|---|
| 36258896621 | 26/09 17:26 | `riepilogo_lacune` -> RPC `season_gaps_summary` (`season_gaps.py:237` di allora) | `APIError {'code': '57014', 'message': 'canceling statement due to statement timeout'}`, traceback | timeout 57014 |
| 36338805869 | 27/09 17:58 | idem | idem, traceback | timeout 57014 |
| 36615357543 | 29/09 19:37 | referto finale | `BUCO VECCHIO: lega 667 stagione 2026 ... API vuota su 9 partite-tabella (in attesa del 2o tentativo)` -> exit 1 | regola d'uscita (buco da API vuota) |
| 36821373801 | 01/10 06:33 | referto finale | `BUCO VECCHIO: lega 10 stagione 2026 ... API vuota su 69 partite-tabella` -> exit 1 | regola d'uscita (buco da API vuota) |
| 37049359939 | 02/10 19:28 | `per_fixture_backfill` lega 344/2026, insert `match_lineups` fixture 1538331 | `<ConnectionTerminated error_code:0, last_stream_id:19999>` -> partita 'parziale' -> `BUCO VECCHIO: lega 344 stagione 2026 ... errore API ripetuto su 1 partite-tabella` -> exit 1 | connessione HTTP/2 terminata |
| 37141249749 | 03/10 18:18 | `per_fixture_backfill` lega 250/2026, delete `match_player_stats` fixture 1505036 | stesso `ConnectionTerminated ... 19999` -> `BUCO VECCHIO lega 250/2026 errore API ripetuto su 1`; nella stessa run altri 2 BUCO VECCHIO da API vuota (129/2026, 255/2026) | connessione HTTP/2 terminata (+ regola API vuota) |
| 37185437609 | 04/10 08:54 | referto finale (fermata per action concorrente) | `BUCO VECCHIO: lega 129 stagione 2026 ... API vuota su 8 partite-tabella` -> exit 1 | regola d'uscita (buco da API vuota) |
| 37743110569 | 08/10 07:28 | pre-controllo `verifica_migrazione` -> `lacune_stagione` -> RPC `season_detail_gaps` (`season_gaps.py:369` -> `:227`) | `HTTP/2 520`, pagina HTML Cloudflare «supabase.co \| 520: Web server is returning an unknown error», `APIError {'code': 520, 'message': 'JSON could not be generated', details=HTML}`, traceback | gateway 5xx/HTML |

Nessun fallimento di classe API-Football.

Causa per classe:
- **57014** (26-27/09): run precedenti alla correzione R-CATCHUP-2 (commit `0ffc3c65`, 28/09 16:10):
  il codice di allora non gestiva il 57014. Da allora nessuna run rossa per 57014 (le degradate
  esistono e restano verdi). Gia' risolto, gestione invariata.
- **Buco vecchio da «API vuota»** (29/09, 01/10, 04/10 mattina, e 2 dei 3 della 03/10): regola
  d'uscita corretta il 04/10 (commit `cdecd095`, 11:00 UTC: diventano AVVISO, exit 0). Le run
  successive (04/10 sera - 07/10) sono tutte verdi. Gia' risolto.
- **Connessione HTTP/2 terminata** (02/10, 03/10): il server chiude la connessione dopo 10.000
  richieste (GOAWAY, `last_stream_id:19999` = 10.000 stream lato client). httpcore ritenta da solo
  gli stream oltre l'ultimo, ma solleva `RemoteProtocolError` per quello in volo (che il server
  PUO' aver eseguito). Nessun ritentativo nel nostro codice -> partita 'parziale' -> stato
  'errore' -> la lega-stagione aperta da > 3 giorni finisce in BUCO VECCHIO «errore API ripetuto»
  -> exit 1. NOTA: il referto del 04/10 attribuiva anche queste due run all'API vuota; con la
  regola del 04/10 sarebbero rimaste ROSSE. Non era risolto.
- **Gateway 520 HTML** (08/10): nessun ritentativo, eccezione non gestita al pre-controllo -> traceback.
  Non era risolto.

## 2. Correzione

### 2.1 Un solo punto di resilienza: `db_client.py`
- `classifica_guasto_rete(exc)` (`db_client.py:228`): `gateway` (APIError con codice HTTP 5xx/520-524,
  details/message con pagina HTML, PGRST000-003, 08xxx/53300/57P01/57P03), `connessione_terminata`
  (`httpx.RemoteProtocolError`, errori h2/httpcore di protocollo), `timeout_rete`
  (`httpx.TimeoutException`), `connessione` (`httpx.NetworkError`). `None` (mai ritentato) per
  4xx, errori applicativi, **57014** (resta a R-CATCHUP-2) e 53100 (disco pieno: guasto vero).
- `con_ritentativi(fn)` (`db_client.py:280`): 1 esecuzione + 5 ritentativi, attese 2-4-8-16-32 s
  con jitter +-25% (~62 s); ogni tentativo loggato `[RETE] <etichetta>: <classe> (tentativo i/6):
  <errore corto> -> ritento tra X s`; su `connessione_terminata` RICREA il client del thread
  (`rinnova_client`, `db_client.py:243`) prima di ritentare; tutti falliti -> `GuastoRete`
  (`db_client.py:158`, messaggio corto: il titolo della pagina, non 7.800 caratteri di HTML).
  Interruttore: dopo 2 guasti persistenti di fila un tentativo solo per chiamata finche' una
  riesce (niente 62 s per ognuno di 40 blocchi con il DB giu').
- `esegui_con_retry(fabbrica, sb)` (`db_client.py:324`): la fabbrica `lambda c: c.table(...)...`
  si ricostruisce a ogni tentativo sul client CORRENTE (`_client_per`: un client nato da
  `get_supabase_client` o un `ClientResiliente` segue i rinnovi; un finto resta se stesso).
- Prevenzione: `attiva_rinnovo_connessioni(5000)` (`db_client.py:264`) + `get_supabase_client`
  (`db_client.py:75`) conta le richieste con un hook di httpx e crea un client nuovo ogni 5.000
  (il server chiude a 10.000). SOLO nel processo del catchup: i bot non cambiano.
- `ClientResiliente` (`db_client.py:389`, con `_Catena` `:346`): il `sb` del catchup. Copre anche
  i moduli della catena FUORI perimetro che ricevono `sb` (season_aggregates, season_backfill,
  api_quota) senza toccarli; un `insert` puro o una RPC non idempotente si esegue una volta sola.
- Perche' non `Betfair/stream/db.py::_exec_retry` / `net_retry.is_transient`: il marcatore
  "timeout" di `is_transient` prende anche il 57014 ('canceling statement due to statement
  timeout') e le attese sono da bot (3 tentativi, 0,15 s); spostarlo o cambiarlo avrebbe
  cambiato il comportamento dei bot (codice di bot = certificazione sul banco). Lasciato intatto.

### 2.2 Le 16 `.execute()` della catena
- `season_gaps.py`: `lacune_stagione` (:223), `riepilogo_lacune` (RPC a blocchi; `GuastoRete` sul
  blocco -> le sue lega-stagioni in `rinviate_rete`, :353, se il chiamante passa la lista),
  `scrivi_stato`, `scrivi_stati`, `segna_degradato_57014` (lettura + upsert), `leggi_stati`,
  `leggi_coverage`: tutte con `esegui_con_retry` (letture e upsert/update idempotenti).
  `registra_esiti` -> `_registra_una_volta_sola` (:430): la RPC `record_fixture_detail_checks`
  INCREMENTA `vuoti`/`errori` (due 'vuoto' = vuoto_definitivo): prima di ritentarla si legge
  `fixture_detail_checks` e, se il tentativo precedente era arrivato al DB (esito uguale e
  `ultimo_controllo_at` dopo l'inizio, tolleranza 60 s), NON si riapplica.
- `per_fixture_backfill.py`: `get_supabase()` (:83) e' un ACCESSORE (via la variabile
  `_supabase` catturata); coverage, matches, delete con `esegui_con_retry`; l'insert non si
  ritenta da solo (righe doppie se il primo era arrivato): `insert_rows` fa risalire il guasto
  di rete (:274) e `_sostituisci_righe` (:924) ritenta l'UNITA' delete+insert. Guasto persistente
  -> partita 'parziale' (esito vero), niente altre chiamate API per quella partita (:1042),
  esiti non registrabili -> avviso (:1064), lega-stagione fermata con `fermato_per = "guasto
  rete/gateway"` (:1166).
- `seasons_catchup.py`: `_salva_verifica_current` con `esegui_con_retry` (guasto -> avviso, :442).

### 2.3 Exit code (`seasons_catchup.py`)
- Rinvii: dalla verifica (blocco in guasto, escluse da coda, stati e P4 come le degradate 57014,
  :646), dal lavoro (`_e_guasto_rete`, :843; `except GuastoRete`, :727) e dalla P4 (:832): la
  lega-stagione e' RINVIATA (`_rinvia_per_rete`, :850), la run si ferma a fine partita come per la
  quota, contatore dei GIORNI di calendario consecutivi in `stats_json.rinviato_rete`
  (`season_gaps.segna_rinvio_rete`/`giorni_consecutivi`, :583/:570; si azzera da solo alla
  prossima verifica riuscita).
- Referto (`_referto_rete`, :1067): sempre la riga «Rete PostgREST: ritentativi ..., guasti
  persistenti ..., client rinnovati ...»; con rinvii la sezione «RINVIATE PER GATEWAY/RETE» nel log
  e in `GITHUB_STEP_SUMMARY`. Exit 0 se sotto soglia; exit 1 se rinvii > 50% delle lega-stagioni
  considerate (`CATCHUP_SOGLIA_RINVII_RETE_PCT`) o una lega-stagione rinviata da > 3 giorni
  consecutivi (`BACKFILL_BUCHI_MAX_GIORNI`).
- `main` (:1113, :1127): `sb = ClientResiliente()`, rinnovo a 5.000; un `GuastoRete` in una fase
  comune (pre-controlli, letture iniziali, scrittura degli stati) -> titolo «RINVIATE PER
  GATEWAY/RETE: TUTTA LA RUN», riepilogo del job, exit 1, nessun traceback.

### 2.4 Workflow
`.github/workflows/seasons_catchup.yml`: regola dell'08/10 in testa; env
`CATCHUP_RINNOVO_CLIENT_OGNI: '5000'`, `CATCHUP_SOGLIA_RINVII_RETE_PCT: '50'`,
`PYTHONUNBUFFERED: '1'` (nei log di oggi i `print` del catchup uscivano tutti in fondo, staccati
dai log di httpx: per classificare le run ho dovuto ricostruire l'ordine). Nessun cambio di
orari, quote, riserve, priorita'.

File toccati: `db_client.py`, `season_gaps.py`, `per_fixture_backfill.py`, `seasons_catchup.py`,
`.github/workflows/seasons_catchup.yml`. Nuovi: `test_catchup_rete_2026_10_08.py`, questa cartella.

## 3. Test

`python -m pytest test_catchup_*.py -q -p no:cacheprovider` -> **90 passed** (66 dei 4 file
esistenti + 24 nuovi), 6 s. Con i test collegati (`test_backfill_automatico_2026_09_25.py`,
`test_orchestratore_niente_refresh_mv_2026_09_25.py`, `test_daily_niente_aggregati_2026_09_25.py`,
`test_riserva_dinamica_2026_09_25.py`, `test_actions_pipeline_paginazione.py`,
`Betfair/stream/tests/test_db_client_timeout_bot_2026_09_28.py`, `test_net_retry.py`,
`test_replay_scalper_db_isolato_2026_10_06.py`, `test_reconcile_worker.py`): 309 passed.

I finti dei test nuovi: client supabase/postgrest/httpx VERO con `httpx.MockTransport` al posto
della rete. La 520 e' la risposta HTML (inizio e titolo copiati dal log di 37743110569) da cui il
codice vero di postgrest costruisce l'`APIError` (code 520, 'JSON could not be generated');
il GOAWAY e' un `httpx.RemoteProtocolError` con il messaggio vero; 57014, PGRST202, 23505, 42501,
53100, PGRST002 con i corpi JSON veri di PostgREST. Test: classificazione sulle eccezioni vere;
520 poi successo (anche nel punto esatto del traceback, `verifica_migrazione`); GOAWAY poi
successo con client NUOVO (oggetto diverso, richiesta dal client n.1); accessore di
per_fixture; GOAWAY dopo un insert APPLICATO -> nessun doppione; registro esiti arrivato -> non
riapplicato / non arrivato -> riapplicato; 6 esecuzioni fallite -> GuastoRete, attese 2-32 s
+-25%; blocco in guasto -> rinviato e il blocco dopo verificato; interruttore; per_fixture si
ferma e registra 'parziale'; referto sotto soglia exit 0 / oltre soglia exit 1 / persistente
exit 1; giorni (non run) consecutivi; main senza traceback exit 1; 4xx nessun ritentativo;
insert dal proxy mai ritentato; 57014 al meccanismo esistente (1 + 1 + 1 RPC, degradata, zero
attese); rinnovo ogni N e nessun rinnovo senza attivazione; catena intera `esegui_catchup` con
blocco 520 (nessuno stato v2 fabbricato, contatore scritto) e con GOAWAY persistente sull'insert
(rinvio, run fermata, exit 0 a 1 su 2).

### Falsificazione (19 mutazioni, `falsificazione_mutazioni.py`, esito in `falsificazione_esito.txt`)
Tutte ROSSE, ripristino verificato con sha256 file per file, `grep -c MUTAZIONE` = 0, diff dopo =
diff prima (byte per byte).

| Mutazione | Test rossi |
|---|---|
| M01 5xx non ritentati | 9 |
| M02 nessun rinnovo del client su connessione terminata | 2 |
| M03 per_fixture: client catturato in variabile di modulo | 3 |
| M04 ritentato il solo insert (delete fuori dall'unita') | 1 |
| M05 registro esiti riapplicato alla cieca | 1 |
| M06 blocco in guasto: GuastoRete risale anche con la lista | 3 |
| M07 interruttore spento | 1 |
| M08 per_fixture non si ferma al guasto persistente | 2 |
| M09 referto: guasto di rete mai rosso | 3 |
| M10 4xx ritentati | 2 |
| M11 57014 ritentato come guasto di rete | 2 |
| M12 proxy: insert ritentato | 1 |
| M13 nessun rinnovo preventivo | 1 |
| M14 main: GuastoRete non gestito (traceback) | 1 |
| M15 giorni consecutivi = run consecutive | 1 |
| M16 catchup: rinviate non escluse (stato falso scritto) | 1 |
| M17 catchup: GuastoRete nel lavoro trattato come errore | 1 |
| M18 backoff tolto (nessuna attesa) | 3 |
| M19 insert_rows inghiotte il guasto di rete | 2 |

## 4. Prova vera senza scrivere

`seasons_catchup.py` NON ha una modalita' di prova (nessun `--dry-run`): non l'ho inventata.
Fatte due prove in sola lettura contro il DB vero (`.env` del repo), zero scritture, zero
chiamate API-Football contate:
- `sonda_rete_sola_lettura.py` (`prova_vera_sonda.txt`): `ClientResiliente` + rinnovo a 3
  richieste, `lacune_stagione(135, 2025)` (380 FT), `riepilogo_lacune` su 2 coppie, `leggi_coverage`
  e `leggi_stati` della lega 135, una select dal proxy: tutto corretto, 1 client rinnovato dopo
  3 richieste, 0 ritentativi, 3-6 s.
- `python league_orchestrator.py --league 135 --season 2025 --dry-run` (modalita' esistente,
  stessa catena season_gaps/season_backfill/season_aggregates): referto regolare, «Nulla e'
  stato chiamato ne' scritto»; 1 sola richiesta a `/status` di API-Football (non consuma quota).

## 5. Parita' paper/live

Non tocca bot ne' ordini. `db_client.get_supabase_client` per i bot e' identico (il rinnovo
preventivo si accende solo con `attiva_rinnovo_connessioni`, chiamata solo dal main del
catchup; l'unica differenza e' l'attributo `_db_client_prod` sul client creato). Test del
timeout bot (`test_db_client_timeout_bot_2026_09_28.py`) e di `net_retry` verdi.

## 6. Cosa NON ho fatto / NON ho potuto verificare

- NON verificato su GitHub: nessuna run lanciata (vietato `gh workflow run`). La prova vera e' la
  prossima run (stasera ~18:45 UTC o domattina dopo il Leagues Mapping): nel log cercare
  `[RETE]`, la riga «Rete PostgREST: ...» in fondo al referto e, se compare, la sezione
  «RINVIATE PER GATEWAY/RETE» nel riepilogo del job.
- `season_aggregates.py`, `season_backfill.py`, `api_quota.py`, `logger.py` NON toccati (fuori
  perimetro): coperti dal `ClientResiliente` (passa per `sb`), salvo: l'`insert` degli aggregati
  non e' ritentato (non idempotente, come prima: errore -> esito 'errore', ritentato al giro
  dopo); `logger.py` (api_call_log) usa `get_supabase_client` senza ritentativi (telemetria gia'
  best-effort, ma segue il rinnovo preventivo); `fixtures_backfill.backfill_fixtures_for_league_season`
  (P4) usa il suo client senza ritentativi.
- `season_backfill.esegui` inghiotte le eccezioni in una stringa: il rinvio si riconosce dal
  prefisso `"GuastoRete:"` di `es.errore` (stesso formato `f"{type(e).__name__}: {e}"`). Se quel
  formato cambia, il rinvio diventerebbe un errore (exit 1, non un traceback).
- Dopo un guasto persistente su un insert a piu' blocchi (solo `match_odds` supera 200 righe), se
  anche la registrazione dell'esito 'parziale' fallisce le righe parziali possono sembrare piene:
  rischio GIA' esistente, ora molto piu' raro (unita' ritentata ~62 s). Scritto nel log.
- `get_coverage_for_season` usa `maybe_single()`: postgrest trasforma QUALUNQUE errore in
  `APIError 'Missing response' code 204` perdendo l'originale, quindi li' una 520 non si ritenta
  (la funzione ritorna None come prima; nel catchup non e' usata: la coverage e' gia' in memoria).
- Un `ConnectionError` builtin (non httpx) NON e' classificato: httpx non lo lascia mai uscire
  (lo mappa in `httpx.ConnectError`); il test esistente «errore di rete si propaga come prima»
  resta valido.
- Il contatore dei giorni di rinvio si scrive sul DB: con il DB irraggiungibile non si scrive
  (avviso «non scritti»), quindi la regola «> 3 giorni» vale per i guasti intermittenti; il
  guasto totale e' coperto dalla soglia del 50% e dal guasto in fase comune (exit 1).

## 7. Decisioni per l'utente

Nessuna su strategie o recuperi. Una proposta per il coordinatore (fuori perimetro): il rinnovo
preventivo del client ogni 5.000 richieste potrebbe servire anche ai processi lunghi dei bot
(stesso GOAWAY a 10.000), oggi coperti solo dai 3 ritentativi di `_exec_retry`; non l'ho acceso
per i bot.

## 8. Da controllare alla prossima run dell'action

Il log della run (`gh run view <id> --log`): righe `[RETE]` (attese e classe), riga finale
«Rete PostgREST: ritentativi N ..., client rinnovati M» (con ~11.000 richieste per run, M >= 1
atteso), nessun traceback; se il DB ha un guasto lungo: sezione «RINVIATE PER GATEWAY/RETE» nel
riepilogo del job con la percentuale.
