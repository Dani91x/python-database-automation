# FASE 1 (app spenta) dei 65 controlli §7 — admin-26

Delegato del coordinatore (Sonnet 5), worktree isolato, rebase su `origin/master`
(`d771d05`, ≥ `099412c`). Esecuzione: 25/09/2026 pomeriggio. Metodo, SOLA LETTURA:

- sonde REST PostgREST dirette (`GET .../rest/v1/<tabella>?select=...&limit=...`,
  `GET .../rest/v1/rpc/<funzione>?...` SOLO per le RPC esposte in **GET**, cioè
  dichiarate `STABLE`/`IMMUTABLE` da PostgREST — mai una RPC POST-only, che potrebbe
  scrivere);
- introspezione `GET /rest/v1/` (OpenAPI): 322 endpoint, 198 RPC, 123 tabelle/viste,
  usata per verificare esistenza/firma delle funzioni e le colonne vere di ogni
  tabella citata nel piano;
- lettura chiavi di `.env` del checkout principale (nomi, non i valori delle chiavi
  segrete: `API_FOOTBALL_KEY`, `BETFAIR_*`, `GOOGLE_CREDENTIALS_FILE`,
  `SUPABASE_SERVICE_ROLE_KEY` MAI stampate; i flag di configurazione non segreti,
  es. `HAZARD_ATLAS_SYNC`, sono stati letti anche nel valore);
- `git log`/`gh run view --log` (log reale dell'ultimo run `seasons_catchup.yml`,
  id `36122837946`, completed/success);
- dry-run REALE: `python league_orchestrator.py --league 135 --season 2026 --dry-run`
  (exit 0, nessuna chiamata API a pagamento — solo REST Supabase interni, nessuna
  scrittura, vedi §7.4.8);
- `pytest` sui file di test GIA' esistenti nel repo (nessuna scrittura, mock/fixture
  proprie, nessun accesso DB): 82+159+32+15 = 288 test eseguiti, tutti verdi, elencati
  sotto per ogni sottosezione;
- grep sul codice sorgente per i log/testi/soglie attesi.

**Criterio adottato per PASS vs FASE 2** (dichiarato per trasparenza, nessuna
iniziativa presa sul piano): un controllo è **PASS** in fase 1 se la sua evidenza è
una proprietà del CODICE/CONFIG/MIGRAZIONE/SCHEMA (formato di un testo, soglia,
esistenza di una RPC/colonna, contenuto di un log GH Actions già girato) verificabile
in modo completo e falsificabile senza il processo vivo — inclusi i casi in cui la
prova è un test unitario ESEGUITO ora (non solo letto) che pinna esattamente quella
soglia/quel testo con dati finti. È **FASE 2** quando l'asserzione riguarda un VALORE
calcolato dal vivo, un CONFRONTO fra due letture in tempi diversi, o una SEQUENZA di
azioni (clic, riavvio, accensione/spegnimento) che solo l'app viva produce. Nessun
controllo è stato dichiarato PASS solo perché "il codice esiste": dove ho trovato un
test dedicato l'ho rieseguito; dove non c'era (frontend, `node_modules` assente nel
worktree — non installato, per non toccare il checkout principale) resta scritto che
è stato verificato per grep, non per test eseguito.

**Non un solo FAIL trovato nei 65 controlli.** Tre note di trascrizione nel piano
(non difetti del codice), segnalate sotto ai punti relativi:
1. §7.4.8 cita `python -m Betfair.stream.backfill.league_orchestrator`: quel modulo
   NON esiste nel repo. Lo script vive in radice: `python league_orchestrator.py
   --league 135 --season 2026 --dry-run` (stesso comando che l'help del file stesso,
   riga 13, dichiara). Eseguito con successo (vedi 7.4.8).
2. §7.3.5 cita `dossier.py:309-321` per le chiavi hazard: le assegnazioni vere sono
   alle righe 340-342 (`hazard_versione`, `hazard_fase`, `hazard_recupero_atteso_min`),
   309-321 è il commento introduttivo del blocco. Stesso file, poche righe più sotto.
3. §7.5.1 cita `bot_service.py:2778`: la scrittura vera di `prezzo_segnale` è alle
   righe 2825-2827. Stesso file.

## Riepilogo per sottosezione

| Sottosezione | PASS | FASE 2 | FAIL |
|---|---|---|---|
| 7.1 Feed unico | 0 | 4 | 0 |
| 7.2 Auto-follow e strada ordini | 1 | 12 | 0 |
| 7.3 Atlante v4 | 4 | 4 | 0 |
| 7.4 Catchup e referto buchi | 8 | 0 | 0 |
| 7.5 Schede B17 | 6 | 2 | 0 |
| 7.6 Scalper auto-mode | 3 | 5 | 0 |
| 7.7 Tennis auto-mode | 6 | 2 | 0 |
| 7.8 Safe: veti aggiuntivi | 8 | 0 | 0 |
| **Totale** | **36** | **29** | **0** |

Nessun FAIL: nessuna correzione da proporre. Le 29 voci FASE 2 sono elencate con il
valore atteso, da riverificare quando l'app è accesa (nella stessa forma già scritta
dal piano, §7).

---

## 7.1 Feed unico (0 PASS / 4 FASE 2)

| # | esito | evidenza |
|---|---|---|
| 7.1.1 | **FASE 2** — atteso: `event_id`/età coincidenti fra `safe_strategy_scan` (sport calcio) e la nota `stats.auto` di `scalper_service_control` | verificato ORA (sola lettura): `scalper_control` ha **0 righe** con `origine='auto'` in tutta la tabella; `scalper_service_control` = `{status:stopped, mode:paper, stats:null}`. Nessun evento armato dallo scalper da confrontare oggi: il confronto richiede lo scalper auto-mode acceso e una partita realmente armata. |
| 7.1.2 | **FASE 2** — stesso controllo lato tennis (`safe_strategy_scan` sport tennis vs `tennis_bot_service_control`) | `tennis_live_follow` ha **0 righe** con `origine='auto'`; `tennis_bot_service_control` mostra tutti i 4 bot a `status=stopping`, `heartbeat_at` fermo al 24/09 (stale, app spenta). |
| 7.1.3 | **FASE 2** — atteso: nessuna nuova riga `origine='auto'` mentre lo scanner è vecchio (>30 s) | richiede di fermare lo scanner IN TEST (azione sull'app viva), non riproducibile da sonda. |
| 7.1.4 | **FASE 2** — atteso: log `[auto-follow] seguiti da soli X eventi (Y mercati) … feed F partite (db)` con `F` coerente a `select count(*) from safe_strategy_scan where sport='calcio' and updated_at > now()-interval '30 seconds'` | il log richiede il runner in esecuzione; nessuna riga recente in `safe_strategy_scan` da confrontare (scanner fermo). |

**Nota:** nessun evento con `origine='auto'` esiste oggi in nessuna delle tabelle di
follow (`scalper_control`, `live_follow`, `tennis_live_follow`): conferma indipendente
che l'auto-mode non è mai stato esercitato dal vivo sul DB reale finora — la fase 2
partirà da zero su questo fronte.

## 7.2 Auto-follow e strada unica degli ordini (1 PASS / 12 FASE 2)

| # | esito | evidenza |
|---|---|---|
| 7.2.1 | **FASE 2** — log `[runner] AUTO-FOLLOW ATTIVO: …` all'avvio | stringa confermata nel codice: `Betfair/stream/runner.py:1906`. Compare solo all'avvio del runner (app spenta ora). |
| 7.2.2 | **FASE 2** — log `[runner] motore ordini ATTIVO sul canale 47331 …` | stringa confermata: `Betfair/stream/runner.py:1921` (`"[runner] motore ordini ATTIVO sul canale %d (diario %s)"`). |
| 7.2.3 | **FASE 2** — attività `canale_inviato` su `safe_strategy_activity` dopo un'apertura Safe paper | log confermato nel codice: `Betfair/safe_strategy/bot_service.py:876` (`"[safe.bot] ordini %s via canale di comando %s"`). Verificato ORA: **0 righe** `kind='canale_inviato'` in `safe_strategy_activity` (mai esercitato). |
| 7.2.4 | **FASE 2** — marcature `meta->>'canale_ref'` ecc. su `safe_strategy_trades` | schema confermato (`safe_strategy_trades.meta` è jsonb, colonna presente); nessuna riga con quelle chiavi oggi (nessun trade via canale). |
| 7.2.5 | **FASE 2** — età del comando nel diario `_diario_ordini` < 3000 ms | il diario è un file locale dell'app viva, non accessibile a app spenta. |
| 7.2.6 | **FASE 2** — log `[omega] ordini via canale di comando …` | stringa confermata: `Betfair/omega/omega_service.py:2863`. |
| 7.2.7 | **FASE 2** — 0 righe nuove su `betfair_live_order_requests` dopo un ordine via canale | verificato ORA: ultima riga della tabella è del **10/07/2026** (id 99) — nessuna attività recente, coerente con app spenta; il controllo vero e proprio (0 righe DURANTE un ordine via canale) resta da fare in fase 2. |
| 7.2.8 | **FASE 2** — aggancio al volo entro 3000 ms | richiede un comando reale su una partita non seguita. |
| 7.2.9 | **FASE 2** — 0 occorrenze di «market … non sottoscritto nel runner» durante la fase 2 | messaggio (il vecchio rifiuto) confermato nel codice: `Betfair/stream/live_order_worker.py:693`; conteggio sul log reale è per costruzione un controllo di fase 2. |
| 7.2.10 | **FASE 2** — tetto 180 mercati rispettato con follow manuali | richiede seguire 2-3 partite a mano e accendere i bot; `LIVE_MARKET_TYPES` risulta **assente** da `.env` (coerente con l'osservazione già scritta dal piano stesso, §"Osservazioni" punto 1). |
| 7.2.11 | **FASE 2** — righe `live_follow.origine='auto'` coerenti (`STREAMING` mentre seguite, `CLOSED` al riavvio) | schema confermato: `live_follow` ha la colonna `origine`; **0 righe** `origine='auto'` oggi (verificato ORA). |
| 7.2.12 | **FASE 2** — riga passa `error`/`canale_senza_esito` dopo TTL+60s al riavvio con un comando parcheggiato | scenario di riavvio, non riproducibile a app spenta. |
| 7.2.13 | **PASS** | `.env` del checkout principale: `MIKE_USE_FLUMINE_QUEUE` **assente**, `SAFE_TENNIS_ORDINI_VIA_CANALE` **assente** (grep diretto, nessun valore stampato perché sono flag booleani non segreti ma comunque assenti). Mike e Safe tennis restano su REST, nessuna accensione non autorizzata. |

## 7.3 Atlante v4 (4 PASS / 4 FASE 2)

| # | esito | evidenza |
|---|---|---|
| 7.3.1 | **PASS** | `.env`: `HAZARD_ATLAS_SYNC=1` (grep diretto, valore non segreto). |
| 7.3.2 | **FASE 2** — log `[atlante-domanda] …` con leghe v3→v4 | stringhe confermate nel codice (`Betfair/stream/scalper/atlante_a_domanda.py:167,184,208,450,456`); la generazione richiede il thread Safe vivo. |
| 7.3.3 | **FASE 2** — righe `hazard_atlas_leghe` con `ha_v4=true` | **`hazard_atlas_leghe` è VUOTA: 0 righe** (query reale `select ... from hazard_atlas_leghe limit 5` → `[]`). Nessuna lega ha ancora stato v4 scritto: il generatore non ha mai girato su questo DB. **Da segnalare al coordinatore come punto da sorvegliare all'avvio della fase 2** (non un difetto: `HAZARD_ATLAS_SYNC` è stato acceso solo oggi 25/09 h13:05, coerente col piano). Schema confermato via OpenAPI: `league_id, league_name, n_fixtures, last_fixture_date, updated_at, stato jsonb, fixtures jsonb` — combacia esattamente con quanto scritto dal piano stesso (Osservazioni, punto 3). |
| 7.3.4 | **PASS (test statico)** | formato a due varianti confermato nel codice `Betfair/safe_strategy/opportunity.py:706-712` (`versione_txt = f"{etichetta_versione(consulta)}, {consulta.get('fase')}"` con eventuale «, recupero atteso ancora N'»; altrimenti `"atlante v3: recupero non modellato (...)"`); `etichetta_versione` in `Betfair/stream/scalper/atlante_v4.py:827-829` produce `"atlante v4 (A*)"` o `"atlante v4 (A1+A2)"` (il piano parafrasa "atlante v4,": combacia, il prefisso reale è più specifico, non un errore). **Rieseguito `pytest Betfair/stream/tests/test_atlante_v4_collegato_2026_09_25.py`: 32/32 verdi**, incluse le asserzioni sul testo della nota (righe 219, 447, 475 del test). La riga reale su una proposta/trade con dati di mercato veri resta da osservare in fase 2 (nessuna proposta ESATTO generata oggi, app spenta). |
| 7.3.5 | **FASE 2** — `hazard_versione`/`hazard_fase`/`hazard_recupero_atteso_min` su `mike_events.live` | codice conferma le 3 chiavi: `Betfair/mike/dossier.py:340-342`. Verificato ORA sulle righe reali più recenti di `mike_events` (25/09... in realtà le 3 più recenti sono del 24/09 e 17/09, stale): contengono `hazard_atlas`/`hazard_model` ma **non ancora** `hazard_versione`/`hazard_fase`/`hazard_recupero_atteso_min` — righe scritte prima che la funzione fosse in produzione su dati vivi. Non un difetto: serve un ciclo Mike vivo DOPO l'accensione di `HAZARD_ATLAS_SYNC` per popolarle. |
| 7.3.6 | **FASE 2** — `hazard_recupero_atteso_min` volatile, `hazard_versione`/`hazard_fase` stabili fra due letture a 60 s | richiede una partita in recupero dal vivo, per costruzione irriproducibile a app spenta. |
| 7.3.7 | **PASS** | query reale `select payload from omega_activity where kind ilike '%hazard%' order by ts desc limit 5` → **`[]`, 0 righe**. Omega non ha mai scritto attività "hazard": coerente con "Omega non consuma hazard" per tutta la storia della tabella, non solo oggi. |
| 7.3.8 | **PASS (test statico)** | ripiego dichiarato con motivo confermato nel codice: `Betfair/safe_strategy/opportunity.py:711-712` e `Betfair/stream/scalper/atlante_v4.py:653` (`"atlante v3: recupero non modellato ({motivo})"`, mai generico). Stessa esecuzione di `test_atlante_v4_collegato_2026_09_25.py` (32/32 verdi) copre il caso "blocco v4 assente" e "lega non nel v4". |

## 7.4 Catchup e referto buchi (8 PASS / 0 FASE 2)

| # | esito | evidenza |
|---|---|---|
| 7.4.1 | **PASS** | OpenAPI (`GET /rest/v1/`): le 3 funzioni `record_fixture_detail_checks`, `season_detail_gaps`, `season_gaps_summary` sono tutte presenti come RPC esposte. Migrazione `season_gaps_2026-09-25.sql` applicata. |
| 7.4.2 | **PASS** | RPC eseguita realmente (sola lettura, funzione `STABLE`/GET): `GET /rest/v1/rpc/season_detail_gaps?p_league_id=135&p_season_year=2026&limit=5` → **HTTP 200**, risposta in < 1 s, 3 righe (`_partite` ft/tutte, `match_odds` non_disponibile con 40 fixture_ids). Nessun timeout 57014: l'indice utile è presente. |
| 7.4.3 | **PASS** | log reale dell'ultimo run `seasons_catchup.yml` (`gh run view 36122837946 --log`, run completed/success 2026-09-25T10:13Z): tabella "REFERTO BUCHI" con le colonne attese (Lega/Stag/P/FT/da chiamare ev-fo-sg-ss-qu/att./costo~/aperto da) e riga finale `"BUCHI APERTI: 961 lega-stagioni, ~122875 chiamate, il piu' vecchio da 0 giorni"` (formato esatto atteso dal piano). |
| 7.4.4 | **PASS** | stesso log: **0 occorrenze** di `"BUCO VECCHIO"` — coerente con "il più vecchio da 0 giorni" della riga finale (nessun buco ha ancora superato i 3 giorni). |
| 7.4.5 | **PASS** | stesso log: `"[CATCHUP] quota all'avvio: contatore API 1318/7500 (fonte /status), riserva action 3000, margine 3182"` — margine = 7500 − 1318 − 3000 = 3182, coerente con la riga stessa. |
| 7.4.6 | **PASS** | query reale `select league_id, season_year, status, stats_json from season_backfill_state order by updated_at desc limit 20`: tutte le 20 righe più recenti sono `in_progress` con `buchi_aperti>0` (coerente: stagione 2026 in corso, `current=true`). Query mirata per la regressione: `status=eq.completed AND stats_json->>buchi_aperti != 0` → **0 righe** (nessuna violazione della regola "`completed` solo se zero buchi aperti"). Le righe `completed` esistenti sono vecchie (v1, giugno, senza chiave `buchi_aperti`: predatano il formato v2, non è una regressione). |
| 7.4.7 | **PASS** | `seasons_catchup.py:57-58`: `WORKFLOW_ESCLUSIVI_DEFAULT = ("daily_yesterday_backfill.yml", "today_predictions_backfill.yml", "predictions_results_backfill.yml", "retrain_models.yml")` — `retrain_models.yml` incluso oltre a Daily/Today/Results. |
| 7.4.8 | **PASS** | dry-run REALE eseguito: `python league_orchestrator.py --league 135 --season 2026 --dry-run` → **exit 0**, nessuna chiamata API-Football (solo richieste REST verso Supabase, tutte lette dal log httpx: RPC `season_detail_gaps`/`season_aggregates_summary`, GET su `api_coverage_by_season`/`season_backfill_state`/`api_call_log`), output finale `"Nulla e' stato chiamato ne' scritto."`. **Nota di trascrizione nel piano**: il comando citato (`python -m Betfair.stream.backfill.league_orchestrator`) non esiste; lo script è in radice (`league_orchestrator.py`, come dichiara il suo stesso help a riga 13). |

## 7.5 Schede B17 (6 PASS / 2 FASE 2)

| # | esito | evidenza |
|---|---|---|
| 7.5.1 | **PASS (test statico)** | scrittura confermata: `Betfair/safe_strategy/bot_service.py:2825-2827` (`meta["prezzo_segnale"] = segnale`, non riga 2778 come cita il piano — stesso file, poco più sotto). Rieseguito `pytest Betfair/safe_strategy/tests/test_prezzo_segnale_b17_2026_09_25.py`: **incluso nei 15/15 verdi** (vedi riepilogo comando sotto). Nessuna riga reale con `meta->>'prezzo_segnale'` oggi (verificato: `0` righe) — nuovo, mai esercitato dal vivo. |
| 7.5.2 | **PASS (test statico)** | stesso file di test copre il contesto della richiesta (`test_il_contesto_conserva_il_segnale_solo_se_valido`, `test_il_segnale_del_contesto_arriva_sulla_riga`), 15/15 verdi. Nessuna riga reale oggi (verificato: 0 righe in `safe_strategy_requests` con `payload->>prezzo_segnale`). |
| 7.5.3 | **PASS** | firma RPC dall'OpenAPI: `omega_request_approve(p_id bigint REQUIRED, p_price numeric DEFAULT NULL, p_contesto jsonb DEFAULT NULL)` — è la firma NUOVA (migrazione `omega_request_approve_contesto_2026-09-25.sql` applicata), non quella vecchia a `p_id` solo. Rieseguito `pytest Betfair/omega/tests/test_omega_approve_contesto_b17_2026_09_25.py`: verde (nei 15/15). |
| 7.5.4 | **PASS (parziale)** | backend: kind `approva_uscita` e verifica `chiave` confermati da `Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py` (rieseguito, verde, nei 159/159 sotto). Frontend (`PropostaUscitaMike.tsx`): `prezzo_segnale`/`clic_ms` presenti nel contesto per grep, **non eseguito con vitest** (nessun `node_modules` nel worktree; non installato per non toccare il checkout principale senza permesso). |
| 7.5.5 | **PASS (grep, non test eseguito)** | tutti e 5 i formati confermati testualmente in `frontend/src/lib/esitoAbbinamento.ts`: righe 428 (ABBINATO TOTALMENTE), 430 (PARZIALMENTE), 438/503 (NON abbinato FOK), 441/508 (rifiutato), più `frontend/src/components/controlroom/EsitoAbbinamentoStriscia.tsx:44` (cartellino "paper · abbinamento simulato"). Piccola differenza tipografica: il codice usa l'apostrofo tipografico (’) dove il piano scrive quello dritto ('), non sostanziale. `vitest` non eseguito (vedi nota sopra). |
| 7.5.6 | **PASS (grep, non test eseguito)** | le 3 forme confermate in `frontend/src/lib/esitoAbbinamento.ts:465-469` e pinnate da `esitoAbbinamento.test.ts` (righe 229, 261, 271, 276-277) e `EsitoAbbinamento.schede.test.tsx` (righe 109, 153) — non rieseguiti (`vitest` assente). |
| 7.5.7 | **FASE 2** — comportamento del "Chiudi" per bot | richiede clic live su ciascun bot e osservazione della gamba/riga risultante; nessuna evidenza statica sufficiente (è un comportamento di integrazione, non un singolo testo). |
| 7.5.8 | **FASE 2** — punto esplicitamente lasciato aperto dal piano stesso ("da portare all'utente se emerge in fase 2") | nota di supporto: `Betfair/safe_strategy/tests/test_esecuzione_a_mercato_d7_2026_09_25.py` esiste ed è stato rieseguito (verde, nei 82/82 di §7.8) a conferma che l'esecuzione resta a mercato e non a banda; ma il piano stesso qualifica questo punto come osservazione da fare in fase 2, non un pass/fail di forma. |

## 7.6 Scalper auto-mode (3 PASS / 5 FASE 2)

| # | esito | evidenza |
|---|---|---|
| 7.6.1 | **PASS** | OpenAPI: le 4 funzioni `scalper_auto_activate`, `scalper_auto_stop`, `scalper_auto_update`, `scalper_uscite_automatiche` sono tutte presenti come RPC esposte — l'ordine di applicazione delle due migrazioni (`uscite_automatiche_scalper_2026-09-25.sql` prima di `scalper_auto_mode_2026-09-25.sql`) risulta rispettato (entrambe applicate). |
| 7.6.2 | **FASE 2** — rifiuto di `scalper_auto_activate('live')` con lo scalper già `running/paper` | **NON eseguito apposta**: chiamare questa RPC è un'azione (anche se attesa fallire) fuori dal perimetro "sola lettura" del delegato — rischio money-critical se la guardia fosse rotta. Da fare in fase 2 con permesso e sotto osservazione diretta. |
| 7.6.3 | **PASS (test statico)** | `Betfair/stream/scalper/auto_mode.py:70-73`: `TETTO_DEFAULT=2`, `TETTO_MASSIMO=4`, `ENV_TETTO="SCALPER_AUTO_MAX_PARTITE"` (assente da `.env` → userà il default 2, clamp a 4). Rieseguito `pytest Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py`: verde (nei 159/159). Il valore REALE in `scalper_service_control.stats->'auto'->'tetto'` durante l'accensione resta FASE 2 (oggi `stats=null`, mai acceso). |
| 7.6.4 | **FASE 2** — vita sessione (600/4200/7800 s) rispettata su una partita in gioco da più tempo | richiede una partita in-play reale da osservare nel tempo. |
| 7.6.5 | **FASE 2** — stop pulito delle sole sessioni `origine='auto'` a fine partita | richiede una sessione auto reale + una partita che finisce; schema confermato (`scalper_control.origine` esiste), 0 righe `auto` oggi. |
| 7.6.6 | **FASE 2** — riarmo selettivo dopo spegni/riaccendi | sequenza di azioni sull'app viva. |
| 7.6.7 | **PASS (test statico)** | guardia cablata: `Betfair/stream/scalper/scalper_service.py:363` chiama `AA.ferma_al_nuovo_avvio(...)` (stessa funzione generica di Omega/Mike/Safe, `Betfair/stream/avvio_app.py:151`). Rieseguito `test_scalper_auto_mode_2026_09_25.py` (copre la guardia): verde. |
| 7.6.8 | **FASE 2 (per l'intera fase 2)** — `mode='paper'` sempre | snapshot ORA (fase 1, pre-condizione): `select status, mode from scalper_service_control` → `{status: stopped, mode: paper}` — coerente. La sorveglianza per TUTTA la durata della fase 2 resta da fare live. |

## 7.7 Tennis auto-mode (6 PASS / 2 FASE 2)

| # | esito | evidenza |
|---|---|---|
| 7.7.1 | **PASS** | migrazione applicata: RPC `tennis_bot_service_set_uscite` e `tennis_follow_event` presenti nell'OpenAPI (da `migrations/tennis_uscite_manuali_2026-09-25.sql`); colonna `uscite_automatiche` presente su `tennis_bot_control`/`tennis_bot_service_control` (schema confermato). Poiché la migrazione è applicata, il motivo di blocco "migrazione … non applicata" non deve comparire: coerente. |
| 7.7.2 | **PASS (test statico)** | `Betfair/stream/tennis_live/auto_mode.py:54-60`: `TETTO_DEFAULT=5`, `TETTO_MASSIMO=40`, env `TENNIS_AUTO_MAX_PARTITE` (assente da `.env` → default 5). Rieseguito `pytest Betfair/stream/tennis_live/tests/test_tennis_auto_mode_2026_09_25.py`: verde (nei 159/159). |
| 7.7.3 | **PASS (test statico)** | tutti e 6 i messaggi di blocco confermati come costanti nel codice: `Betfair/stream/tennis_live/auto_mode.py:222-258` (`MOTIVO_GUARDIA`, `MOTIVO_FEED_VUOTO`, `MOTIVO_FEED_MUTO`, `MOTIVO_ORIGINE_ASSENTE`, `MOTIVO_TETTO_ZERO`, messaggio "nessuna partita armabile…"). Stessa suite di test rieseguita, verde. |
| 7.7.4 | **FASE 2** — classificazione discrezionali (gatabili) vs protezioni (sempre attive) per bot | richiede osservare entrambe le condizioni dal vivo su un bot a uscite manuali reale; comportamento di integrazione, non un singolo testo statico. |
| 7.7.5 | **PASS (grep, non test eseguito)** | testo `"uscite: sempre automatiche"` confermato in `frontend/src/components/controlroom/UsciteTennis.tsx:43` e pinnato da `UsciteTennis.test.tsx:52` e `tennisAuto.test.ts:87` — non rieseguiti (vitest assente nel worktree). |
| 7.7.6 | **PASS (parziale)** | chiave `posizione_aperta_dal` confermata: `Betfair/stream/tennis_live/auto_mode.py:69` (`CHIAVE_POSIZIONE_APERTA`), scritta in `Betfair/stream/tennis_live/tennis_bot_service.py:794` (`"posizione_aperta_dal": min(aperte) if aperte else None`), pinnata da `test_tennis_auto_mode_2026_09_25.py:498` (rieseguito, verde). L'avviso arancione a video resta grep-only (frontend non eseguito). |
| 7.7.7 | **PASS (grep, non test eseguito)** | testo `"LIVE: le partite nascono in dry-run, nessun ordine reale finché non lo togli per partita"` confermato in `frontend/src/components/controlroom/tennisAuto.ts:108`, pinnato da `tennisAuto.test.ts:72` — non rieseguito. |
| 7.7.8 | **FASE 2** — partita che esce dal feed → righe `stopping`, follow `CLOSED` solo a righe tutte chiuse | richiede una partita in-play reale che termina durante il test. |

## 7.8 Safe: veti aggiuntivi (8 PASS / 0 FASE 2)

Tutti verificati sia per grep del codice sia — dove applicabile — per query REST reale
sul DB vivo. Rieseguito `pytest Betfair/safe_strategy/tests/ -k "veto or h2h or
campionat or fav_super or dog_lay or esecuzione_a_mercato"`: **82/82 verdi**.

| # | esito | evidenza |
|---|---|---|
| 7.8.1 | **PASS** | `Betfair/safe_strategy/veto_campionati.py:143-144`: `f"veto campionato: {voce.nome} (corso)"`. |
| 7.8.2 | **PASS** | `Betfair/safe_strategy/veto_campionati.py:231-232`: `MOTIVO_FINALE_ROUND = "veto finale: round «Final» (API-Football)"`, `MOTIVO_FINALE_NOME = "veto finale: «Final» nel nome evento (Betfair)"` — entrambe le fonti dichiarate come nel piano. |
| 7.8.3 | **PASS** | `Betfair/safe_strategy/veto_campionati.py:233`: `MOTIVO_SQUADRA_FEMMINILE = "veto campionato: calcio femminile (nome squadra) (corso)"`. |
| 7.8.4 | **PASS** | tutte e 3 le forme di nota h2h confermate: `Betfair/safe_strategy/engine.py:968` (formato con N/M partite), `engine.py:1037` (`SELEZIONE_H2H_NESSUNO`), `engine.py:1035` (`SELEZIONE_H2H_ASSENTE`). |
| 7.8.5 | **PASS** | soglia confermata: `Betfair/safe_strategy/engine.py:256`: `"h2hManyGoalsRateMax": 0.58`; minimo scontri: `engine.py:259`: `"h2hMinMeetings": 3`. |
| 7.8.6 | **PASS** | soglia confermata: `Betfair/safe_strategy/engine.py:315`: `"favSuperMax": 1.20`. |
| 7.8.7 | **PASS** | testo e banda confermati: `Betfair/safe_strategy/engine.py:208-209` (`dogLayMin=20, dogLayMax=34`), `engine.py:1234-1235` (`f"Quota banca sfavorita {min}{NDASH}{max}"`, en-dash come atteso). |
| 7.8.8 | **PASS** | query REST reale: `select params->'tennis'->>'backMin' from safe_strategy_control` → **`"1.02"`**. Migrazione `safe_tennis_backmin_102_2026-09-25.sql` applicata e leggibile dal DB, non dal default codice. |

---

## Comandi pytest rieseguiti (elenco per riproducibilità)

```
python -m pytest Betfair/stream/tests/test_atlante_v4_collegato_2026_09_25.py \
  Betfair/safe_strategy/tests/ -k "veto or h2h or campionat or fav_super or dog_lay or esecuzione_a_mercato" -q
  -> 82 passed, 1775 deselected (49.83s)   [nota: la selezione -k ha escluso i test di
     test_atlante_v4_collegato_2026_09_25.py stesso, rieseguito poi per intero sotto]

python -m pytest Betfair/stream/tests/test_atlante_v4_collegato_2026_09_25.py -q
  -> 32 passed (22.43s)

python -m pytest Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py \
  Betfair/stream/tennis_live/tests/test_tennis_auto_mode_2026_09_25.py \
  Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py -q
  -> 159 passed (7.14s)

python -m pytest Betfair/omega/tests/test_omega_approve_contesto_b17_2026_09_25.py \
  Betfair/safe_strategy/tests/test_prezzo_segnale_b17_2026_09_25.py -q
  -> 15 passed (13.62s)
```

Nessuna scrittura sul DB: tutti i test usano fixture/mock propri (verificato dai nomi
e dalla rapidità di esecuzione, coerente con test unitari, non di integrazione).

## Non fatto / limiti dichiarati

- `vitest` frontend **non eseguito**: il worktree non ha `frontend/node_modules`
  (nessuna junction verso il checkout principale creata per questo delegato) e non è
  stato eseguito `npm install` per non toccare il checkout principale senza permesso
  esplicito. Le verifiche 7.5.5, 7.5.6, 7.5.4(lato UI), 7.7.5, 7.7.6(lato UI), 7.7.7
  sono quindi per grep del sorgente, non per test eseguito: il testo esiste
  letteralmente nel file, ma non ho fatto girare l'asserzione automatica.
- 7.6.2 non eseguito apposta (azione, non sola lettura, rischio money-critical).
- Nessuna chiamata a `record_fixture_detail_checks` (RPC POST-only, presumibilmente
  scrivente): verificata solo l'esistenza, non invocata.
- `hazard_atlas_leghe` risulta VUOTA oggi: non un difetto dei controlli, ma un fatto
  operativo da sapere prima di iniziare la fase 2 (nessuno stato v4 già scritto).
