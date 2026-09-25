# Backfill: tre chiusure circoscritte (25/09/2026)

Delegato del coordinatore, worktree `agent-a6b9f9e7eb5f83ecc`, base `9cbfe76` (gia' aggiornato,
nessun rebase necessario). Niente commit, niente push, niente `git add -A`, nessuna scrittura
sul DB vero. Sandbox per tutti i lanci pytest:
`SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x API_FOOTBALL_KEY=x`.

Decisioni dell'utente (testuali): «1) A 2) A, cancellazione fallita, si riprova, non voglio
buchi nel database o dati doppi. 3) A».

File NON toccati (vincolo): `per_fixture_backfill.py`, `seasons_catchup.py`,
`leagues_mapper.py`, `.github/workflows/*` — confermato (`git status --porcelain -- <file>`
vuoto per tutti e 3 + `.github/`).

---

## 1. Ramo morto degli aggregati tolto dal Daily

### Prima -> dopo

| Prima | Dopo |
|---|---|
| `daily_yesterday_backfill.py:16-20` importava `backfill_standings_for_league_season`, `backfill_top_scorers_for_league_season`, `backfill_top_assists_for_league_season`, `backfill_top_cards_for_league_season`, `backfill_injuries_for_league_season` | import tolti |
| `:310-326` `run_aggregates_for_seasons(season_keys)`: per ogni `(league_id, season_year)` leggeva `get_coverage_for_season` (`per_fixture_backfill.py:97-146`) e testava `coverage.get("standings")`/`"top_scorers"`/`"top_assists"`/`"top_cards"`/`"injuries")` | funzione rimossa; **fatto verificato**: `get_coverage_for_season` (`per_fixture_backfill.py:102-108`, non toccato) costruisce il dict con SOLO le chiavi `events, lineups, team_stats, player_stats, odds` — `coverage.get("standings")` era sempre `None`, il ramo non scattava mai |
| `:358` `run_daily_backfill_for_date` chiamava `run_aggregates_for_seasons(season_keys)` dopo il per-fixture | chiamata tolta; resta un commento di 3 righe (`daily_yesterday_backfill.py:303-307`) che indica dove vivono ora gli aggregati: `seasons_catchup.py` + `season_aggregates.py` (commit `9cbfe76`) |

Nessuna altra funzione produttiva chiamava `backfill_standings_for_league_season` ecc. (confermato
con `grep -rn` sul repo): dopo la rimozione restano solo i loro `__main__`/CLI interattivi nei
5 script storici stessi (usabili a mano).

### Test e falsificazione

Nuovo file `test_daily_niente_aggregati_2026_09_25.py` (2 test):
- `test_dyb_non_importa_piu_le_funzioni_di_aggregato`: guardia strutturale, nessuno dei 6 nomi
  (`run_aggregates_for_seasons` + le 5 `backfill_*_for_league_season`) e' piu' un attributo del
  modulo.
- `test_daily_con_fixture_di_ieri_non_chiama_mai_gli_aggregati`: esegue l'intero
  `run_daily_backfill_for_date("2026-09-24")` con una fixture FT vera, finti API/`upsert`/
  `run_per_fixture_for_date`; le 5 funzioni di aggregato sono piazzate come finti-che-esplodono
  **sul namespace di `daily_yesterday_backfill`** (non sul modulo origine, `raising=False`): se
  il ramo tornasse — anche come nuovo `from standings_backfill import
  backfill_standings_for_league_season` in testa al file — la chiamata risolverebbe comunque quel
  nome, perche' Python legge i globali del modulo a runtime, non al momento dell'import.

**Falsificazione eseguita di persona** (non solo dichiarata): ho reintrodotto temporaneamente in
`daily_yesterday_backfill.py` l'import + una chiamata incondizionata a
`backfill_standings_for_league_season` dentro `run_daily_backfill_for_date`, rilanciato
`test_daily_niente_aggregati_2026_09_25.py` -> **2/2 test rossi**
(`AssertionError: backfill_standings_for_league_season chiamata dal Daily: ramo morto
reintrodotto`), poi ripristinato il file com'era (verificato `git diff --stat` torna alle sole 32
righe del fix vero) e rilanciato -> di nuovo verde.

Suite esistenti mantenute verdi (rilanciate, non solo assunte): `test_actions_fail_rumoroso_
2026_09_25.py` e `test_backfill_automatico_2026_09_25.py` — **55/55 passati**. Ho dovuto togliere
una riga (`test_actions_fail_rumoroso_2026_09_25.py:168`,
`monkeypatch.setattr(dyb, "run_aggregates_for_seasons", lambda keys: None)`) perche' l'attributo
non esiste piu' e `monkeypatch.setattr` senza `raising=False` fallisce su un attributo assente;
nessun'altra riga toccata, nessuna asserzione cambiata.

---

## 2. Cancellazione fallita: si RIPRENDE, mai buchi ne' doppioni

### Helper condiviso (nuovo)

`db_delete_retry.py` (nuovo file, root) — cercato PRIMA se esisteva gia' un helper di ritentativo
(`grep -n "retry\|ritent" db_client.py per_fixture_backfill.py api_quota.py season_aggregates.py`
e ricerca repo-wide `def.*retry\|def.*ritent`): non c'era nulla di riusabile per questo caso (i
risultati erano tutti altri domini, es. Betfair). `delete_con_ritentativi(azione, *, etichetta,
tentativi=3, attese=(2,5,10), dormi=None)` (`db_delete_retry.py:21-48`): esegue `azione` fino a 3
volte, attesa crescente tra un fallimento e il successivo, rilancia l'ultima eccezione se fallisce
anche l'ultimo tentativo. **Nota tecnica verificata sul campo**: `dormi` NON e' un default di
parametro (`= time.sleep`) ma risolto dentro il corpo (`dormi = dormi or time.sleep`,
`db_delete_retry.py:35`) — un default di parametro cattura l'oggetto funzione UNA volta all'
import del modulo e un `monkeypatch.setattr(db_delete_retry.time, "sleep", ...)` fatto dopo non lo
tocca piu'; con la risoluzione a runtime, patchare `db_delete_retry.time.sleep` (stesso oggetto
modulo singleton di `sys.modules["time"]`) funziona. Ho scoperto e corretto questo bug scrivendo
il primo test (altrimenti i test avrebbero dormito per davvero 2+5=7s per caso).

### 5 script storici + season_aggregates.py

| File | Funzione | Prima | Dopo |
|---|---|---|---|
| `standings_backfill.py` | `delete_existing_standings` (:222-262) | try/except: loggava e continuava; l'orchestratore (`backfill_standings_for_league_season`, :332) chiamava `insert_rows_standings` subito dopo comunque | delete incapsulata in `_delete()`, passata a `delete_con_ritentativi` (:254-257); su fallimento definitivo **rilancia** (`raise`, :265) -> l'orchestratore non arriva mai all'insert |
| `injuries_backfill.py` | `delete_existing_injuries` (:192-232) | idem | idem (:224-227, raise :235) |
| `top_scorers_backfill.py` | `delete_existing_top_scorers` (:218-258) | idem | idem (:250-253, raise :261) |
| `top_assists_backfill.py` | `delete_existing_top_assists` (:218-258) | idem | idem (:250-253, raise :261) |
| `top_cards_backfill.py` | `delete_existing_top_cards` (:227-267) | idem | idem (:259-262, raise :270) |
| `season_aggregates.py` | `esegui_aggregato` (:155-186) | delete diretta, un fallimento -> `'errore'` **senza ritentativo** (comportamento gia' corretto su "niente insert dopo delete fallita", ma senza riprovare) | delete passata a `delete_con_ritentativi` (:177-180) PRIMA di dichiarare `'errore'`; un insert fallito dopo delete OK resta `'parziale'` (comportamento gia' esistente, **confermato con test**, non cambiato) |

Ogni `backfill_*_for_league_season` non aveva un `try/except` proprio attorno alla chiamata a
`delete_existing_*`: l'eccezione risale al chiamante e, dai 5 `__main__`/`ask_and_run_cli()`, fa
uscire lo script con traceback non gestito = **exit code != 0** (verificato: nessun catch-all
introdotto o rimosso in quei CLI).

### Test e falsificazione

Nuovo file `test_delete_ritentativi_2026_09_25.py` (21 test):
- **`db_delete_retry` (unit, 4 test)**: fallisce 2 volte poi riesce -> 3 chiamate, attese
  `[2, 5]`; fallisce sempre -> rilancia dopo 3 tentativi, attese `[2, 5]`; primo colpo -> nessuna
  attesa; falsificazione dell'helper stesso con `tentativi=1` (nessun ritentativo) -> risale
  subito.
- **5 script storici (parametrizzati su standings/injuries/top_scorers/top_assists, + 2 test
  dedicati per top_cards che ha 2 fetch)**: delete fallisce 2 volte poi riesce -> 3 tentativi di
  delete, **insert eseguito una volta sola** (no doppioni); delete fallisce sempre -> **zero
  insert**, `RuntimeError` con `"57014"` propagata (finto errore Postgres realistico).
- **Falsificazione parametrizzata** (`test_falsificazione_senza_ritentativo_2_fallimenti_bastano_
  a_bloccare`): forzando `tentativi=1` sull'helper, una delete che fallirebbe solo la prima volta
  (poi riuscirebbe con 3 tentativi) non arriva mai all'insert -> dimostra che e' il ritentativo a
  fare la differenza.
- **`season_aggregates.esegui_aggregato` (3 test)**: delete fallisce 2 volte poi riesce -> esito
  `'righe'`, insert una volta; delete fallisce sempre -> esito `'errore'`, zero insert, 3
  tentativi di delete; delete OK + insert fallito -> esito `'parziale'` (verifica esplicita
  richiesta dall'utente sul comportamento gia' presente, non modificato).

**Falsificazione eseguita di persona** su codice reale (non solo sull'helper isolato): ho
ripristinato temporaneamente in `standings_backfill.py` il vecchio `delete_existing_standings`
(try/except che inghiotte, nessun ritentativo) e rilanciato la suite filtrata su `standings` ->
**3/3 rossi** (`DID NOT RAISE RuntimeError` sui test "insert una volta"/"nessun insert"/
falsificazione parametrizzata); ripristinato il file (`git diff --stat` torna a +15/-3 righe come
il fix vero). Stesso esercizio su `season_aggregates.py` (`esegui_aggregato` senza
`delete_con_ritentativi`) -> **2/2 rossi** (`AssertionError: assert 'errore' == 'righe'` e
`assert 1 == 3` sui tentativi di delete); ripristinato e riverificato verde.

Aggiornato anche il docstring di modulo `season_aggregates.py:25-29` (non piu' accurato: diceva
"gli script storici... INSERISCONO lo stesso = righe doppie", ora falso dopo il fix del punto 2).

---

## 3. Refresh della MV tolto dall'orchestratore

### Prima -> dopo

| Prima | Dopo |
|---|---|
| `league_orchestrator.py:49-55` `refresh_coverage_mv()`: `get_supabase().rpc("refresh_api_coverage_by_season_v2_mv", {}).execute()`, try/except che logga e continua | funzione rimossa, commento di 2 righe (`:49-51`) su dove riprendere (migrazione, quando l'utente vorra') |
| `:195` (numerazione prima del fix) `backfill_full_league`, ramo non-dry-run, chiamava `refresh_coverage_mv()` a fine corsa, **sempre**, anche a zero chiamate | chiamata rimossa |

Confermato con `grep -rln "refresh_api_coverage_by_season_v2_mv\|refresh_coverage_mv"
--include="*.py" .`: prima dell'intervento l'unico riferimento produttivo nel repo era
`league_orchestrator.py` stesso; nessun altro modulo legge quella MV.

### Test e falsificazione

Nuovo file `test_orchestratore_niente_refresh_mv_2026_09_25.py` (3 test), che riusa
l'infrastruttura finta gia' certificata in `test_backfill_automatico_2026_09_25.py`
(`FintoDB`/`FintoServer`/`FintoClient`/`coverage`/`quota_per`, stesso contratto `table()`/`rpc()`
del client supabase-py vero):
- guardia strutturale: `league_orchestrator` non ha piu' l'attributo `refresh_coverage_mv`;
- stagione passata gia' piena (zero chiamate API) -> nessuna RPC `refresh_api_coverage_by_season_
  v2_mv` tra le RPC legittime del giro (`season_detail_gaps`/`season_aggregates_summary`, che
  restano e sono normali);
- stagione con buchi veri (lavoro fatto, `chiamate > 0`, il caso piu' frequente e quello che
  faceva scattare il timeout 57014 in produzione) -> ancora nessuna RPC di refresh.

Ho anche tolto il finto ormai orfano nel test condiviso: `test_backfill_automatico_2026_09_25.py`
aveva un ramo `if self.nome == "refresh_api_coverage_by_season_v2_mv": return _Resp(None)` dentro
`_Rpc.execute()` (nessun test lo esercitava, verificato con `grep`) — rimosso come richiesto
("e il finto nel test se c'e'").

**Falsificazione eseguita di persona**: ho reintrodotto temporaneamente `refresh_coverage_mv()` e
la sua chiamata a fine `backfill_full_league` in `league_orchestrator.py`, rilanciato i 3 test ->
**3/3 rossi** (la guardia strutturale fallisce, e le due liste di RPC mostrano
`refresh_api_coverage_by_season_v2_mv` in coda); ripristinato il file (`git diff --stat` torna a
+3/-8 righe come il fix vero) e riverificato verde.

---

## 4. Numeri delle suite (tutti rilanciati di persona, sandbox sopra, `timeout 600`)

| Suite | Esito |
|---|---|
| `test_actions_fail_rumoroso_2026_09_25.py` + `test_backfill_automatico_2026_09_25.py` (esistenti, mantenuti verdi) | 55/55 |
| `test_daily_niente_aggregati_2026_09_25.py` (nuovo) | 2/2 |
| `test_delete_ritentativi_2026_09_25.py` (nuovo) | 21/21 |
| `test_orchestratore_niente_refresh_mv_2026_09_25.py` (nuovo) | 3/3 |
| **Totale** | **81/81** |

`python -m pyflakes` pulito (exit 0) su tutti i file toccati e nuovi:
`daily_yesterday_backfill.py injuries_backfill.py league_orchestrator.py season_aggregates.py
standings_backfill.py top_assists_backfill.py top_cards_backfill.py top_scorers_backfill.py
db_delete_retry.py` + i 4 file di test.

## 5. File nuovi

- `db_delete_retry.py` — helper condiviso di ritentativo per le DELETE.
- `test_daily_niente_aggregati_2026_09_25.py`
- `test_delete_ritentativi_2026_09_25.py`
- `test_orchestratore_niente_refresh_mv_2026_09_25.py`
- `AUDIT_2026-09-25/BACKFILL_TRE_CHIUSURE.md` (questo file)
- `AUDIT_2026-09-25/backfill_tre_chiusure.patch` (`git diff` completo, 428 righe)

## 6. Non verificato / fuori perimetro (dichiarato, non insabbiato)

- Non ho eseguito un replay/lancio reale degli script `_backfill.py` o dell'orchestratore contro
  Supabase vero o l'API-Football vera (vietato dal mandato: "nessuna scrittura sul DB vero,
  niente rete"). Tutto certificato con finti a chiavi/tipi identici al vero, come richiesto.
  La certificazione di questi tre fix e' quindi **solo unitaria/di integrazione a finti**, non un
  replay del banco comune (non pertinente qui: questi non sono bot Betfair/flumine, sono script
  di backfill DB calcio — il processo standard `PROCESSO_STANDARD_BOT.md` non si applica).
  L'utente ha chiesto solo questi 3 fix circoscritti, non una certificazione end-to-end del
  Daily/orchestratore/aggregati nel loro complesso: quella resta il lavoro gia' fatto e riportato
  in `AUDIT_2026-09-25/BACKFILL_AUTOMATICO_STAGIONI.md` (commit `9cbfe76`).
- Non ho verificato il comportamento di `insert_rows_standings`/`insert_rows_injuries`/ecc. (i 5
  script storici) quando l'INSERT fallisce a meta' dopo una delete riuscita: quella parte del
  codice non e' stata toccata (il mandato copriva solo "cancellazione fallita, si riprova"), resta
  con il suo comportamento originale (logga e continua, nessun raise) — segnalo la asimmetria per
  eventuale decisione futura dell'utente, non l'ho corretta di iniziativa.
  `season_aggregates.esegui_aggregato` invece gestisce gia' l'insert fallito come `'parziale'`
  (confermato con test, non modificato).
- Non ho toccato ne' verificato `seasons_catchup.py` (vietato dal mandato): e' lui che oggi chiama
  `season_aggregates.esegui_aggregato` nel ciclo di recupero automatico, quindi beneficia
  indirettamente del fix del punto 2, ma non ho rilanciato la sua suite (fuori dai file indicati
  come "da toccare"; la sua suite e' comunque dentro `test_backfill_automatico_2026_09_25.py`,
  rilanciata verde sopra).
