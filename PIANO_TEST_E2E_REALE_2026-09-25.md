# PIANO DEL TEST E2E REALE — 25/09/2026 (bozza della sessione B, da revisionare e completare dalla sessione admin-26)

> Ordine dell'utente (testuale): «Appena avrete finito tutti i lavori, faremo il test e2e reale, IL TRADER DEVE
> AVERE DATI VERI E FRESCHI, QUINDI VERIFICATE IN MODO APPROFONDITO; quando sarà finito questo test, accenderemo la
> macchina realmente e tutti i bot in PAPER e vi assicurerete che lavorino come progettato, che utilizzino i dati
> corretti, che diano informazioni corrette ecc, servirà anche un confronto con il db: questo sarà il test più
> approfondito che abbiamo mai fatto, ma solo alla fine e su mia indicazione.»

Autore: delegato Opus della sessione B (admin-9d). SOLO DOCUMENTO: nessun codice, nessun test eseguito, nessun
accesso al DB, nessun processo avviato. Base: `origin/master` = `43e1468` (25/09 16:13). Ogni file:riga qui sotto
l'ho riletto io su quella base; dove non ho trovato il pezzo lo scrivo **«da verificare»**.

Come si legge ogni controllo: **cosa fa ora → cosa ci aspettiamo → come si verifica → cosa vuol dire se non torna**.

---

## 0. Regole che valgono per tutto il test (non negoziabili)

1. **Il test parte SOLO su indicazione dell'utente.** La fase 2 (accensione in paper) parte SOLO su una seconda
   indicazione esplicita, dopo che la fase 1 è chiusa e ripristinata.
2. **I bot li accende solo l'utente, dalla UI.** Nessuno di noi scrive `status='running'` via SQL o script. Il
   coordinatore guida, l'utente clicca; noi leggiamo il DB in SOLA LETTURA per il confronto.
3. **Paper e live non si mischiano mai; calcio e tennis non si mischiano mai** (CLAUDE.md, regola del 14/09).
   In fase 2 NESSUN bot in live, NESSUN «Ordini reali» su LIVE, NESSUN dry-run tolto per partita.
4. **Strategie intoccabili.** Se un controllo mostra una divergenza di strategia, si scrive e si porta all'utente;
   non si corregge durante il test.
5. **Promemoria certificazione (obbligo di `PROCESSO_STANDARD_BOT.md` e `betfair-bot-standard.md`)**: prima di
   dire «paper» all'utente va ricordato lo stato del replay. Stato che risulta dalla cronostoria (25/09, punto di
   ripresa §4): **nessun replay completo è stato eseguito sui cambi del 25/09** (Safe banca 20-34 + veto campionati,
   tennis auto-mode e uscite manuali, uscite automatiche per bot, Omega stato mercato, scalper auto-mode, atlante v4
   collegato, strada unica solo con `--scenari rapidi`). L'ultimo replay completo per bot è c3j/c3k del 24/09.
   Il paper di fase 2 è quindi un paper di codice **non ancora ri-certificato sul banco** per quei cambi: va detto
   all'utente prima della fase 2 (è la sua decisione se fare prima i replay, uno per bot in sequenza).
6. **Un replay per bot, in sequenza, mai in parallelo** (memoria del 24/09); nessun processo nuovo senza permesso;
   mai `git add -A`; nessun commit durante il test.
7. **Il DB si scrive solo dalla UI** (le RPC che la UI chiama). Le uniche scritture SQL ammesse sono quelle del
   **ripristino** (§5), e le lancia l'utente nell'SQL editor dopo averle viste.

---

## 0-bis. Inventario e regola della certificazione globale (aggiunta del coordinatore, 25/09 sera)

Ordine dell'utente (testuale, 25/09 sera): «certificazione globale di ogni singola componente, non date nulla
per scontato, tutte le pagine campo per campo verificate col database». Base dell'inventario: commit `e7d7553`
(11 fork Opus in parallelo, sola lettura su `c9c9a84`) —
`INVENTARIO_COMPONENTI_2026-09-25.md` (482 componenti, `C001`-`C482`, con avvio/vita/spegnimento di ognuna) e
`INVENTARIO_CAMPI_UI_2026-09-25.md` (542 campi a video, `U0001`-`U0542`). Questo piano (§3, §7) copre i
PERCORSI (clic → RPC → DB → servizio) e le PROVE di sistema (§4, §7.1-§7.9); l'inventario copre l'ESAUSTIVITÀ:
ogni componente e ogni campo devono comparire in QUALCHE controllo di QUALCHE fase, con un'evidenza propria
(query, log, screenshot). **Regola dell'utente: senza evidenza = NON CERTIFICATO.** Non basta che un controllo
generico «passi»: se un componente o un campo dell'inventario non ha una riga di evidenza che lo cita per
`id` (C-xxx o U-xxxx), quel componente resta NON CERTIFICATO e va scritto così nel referto finale, non
sottinteso come «coperto dagli altri controlli». La sessione admin-26 (o chi certifica) tiene la mappa
id-inventario → controllo che lo copre; i buchi (componenti/campi senza controllo) si portano all'utente,
non si chiudono da soli.

## 3-bis. Verifica semantica (in aggiunta ai percorsi UI→RPC→DB→servizio di §3 e alle prove di sistema di §7)

Per ogni bot/pagina, oltre a «il clic scrive la riga giusta» (§3) e «il servizio la rilegge» (§4/§7), si verifica
il CONTENUTO nel merito, in sei passi:
- **A — dati in ingresso vs libro vero/IPS a campione:** un campione di righe di `safe_strategy_scan`/feed
  confrontato a mano col book Betfair (Exchange Stream o sito) e con l'IPS (punteggio/minuto) nello stesso istante.
- **B — decisioni ricalcolate con le funzioni di produzione:** MAI reimplementare la logica; si importano le
  STESSE funzioni di produzione (`omega_config.resolve_params`, `bot_service.modalita_di_strategia`,
  `mike/engine.decide`, ecc., già elencate come sonde in §1.7) e si ricalcola la decisione dagli STESSI input
  letti dal DB, confrontando col trade/proposta che è uscito davvero.
- **C — condizioni del manuale per ogni ingresso/mancato ingresso:** per ogni trade aperto (o proposta
  scartata), si verifica che le condizioni documentate della strategia (soglie, veti, banda) fossero TUTTE
  vere (o che almeno una fosse falsa, per uno scarto); si usa la stessa lista di condizioni di §4/§7, non una
  nuova.
- **D — numeri a video vs DB/ricalcolo:** ogni numero mostrato (P&L, esposizione, prezzo medio, stake) si
  confronta con la somma/aggregazione delle righe DB dello stesso perimetro (stesso bot, stessa modalità,
  stesso giorno) E col ricalcolo indipendente del passo B.
- **E — casi subdoli:** righe con `NULL` in un campo atteso, doppie scritture ravvicinate (reperto A del 18/09,
  P12), letture "vince il più recente" quando due fonti (canale/DB) discordano, arrotondamenti al centesimo,
  fusi orari (`updated_at` UTC vs ora locale a video).
- **F — KO con evidenza, nessuna correzione:** ogni divergenza trovata in A-E si scrive come KO con file:riga
  o query di evidenza (stesso formato del catalogo §9-bis) e si porta al coordinatore/all'utente; il test NON
  corregge il codice per farla sparire (regola generale, CLAUDE.md).

## 3-ter. Fase 3 — pagine, campo per campo (dopo la fase 2, su indicazione dell'utente)

Ogni PAGINA della UI, campo per campo, con lo schema: **visto a video → riga DB che lo alimenta → ricalcolo
indipendente (passo B di §3-bis) → tolleranza dichiarata (es. arrotondamento al centesimo, età in secondi) →
coerenza con le ALTRE pagine che mostrano lo stesso numero (mai due verità per lo stesso dato) → caso limite
(riga assente, `NULL`, doppia fonte)**. Ogni campo trovato si spunta con l'`id` di `INVENTARIO_CAMPI_UI` (§0-bis);
un campo non in inventario si aggiunge lì prima di certificarlo. Divisione del lavoro fra le due sessioni
(decisione del coordinatore, evita sovrapposizioni):
- **sessione B:** Dashboard (le 6 tab), Analytics/Reportistiche, pagine Omega/Safe/Mike dedicate, Live P&L
  (`/live-pnl`), sheet dei parametri (`OmegaParamsSheet`/`MikeParamsSheet`/`SafeStrategy` params).
- **sessione admin-26:** Control Room, Segui Live, Market Watch, Tennis Terminal.

---

## 1. Prerequisiti

### 1.1 Migrazioni: applicate / da applicare (verificare PRIMA, in sola lettura)

Fonte: cronostoria 25/09 e file in `migrations/`. «Applicata» = dichiarata applicata e verificata in cronostoria.

| migrazione | stato secondo la cronostoria | serve a | verifica (sola lettura) |
|---|---|---|---|
| `live_order_mode_control_2026-09-24.sql` | applicata (24/09 h16:15) | Ordini reali OFF/PAPER/LIVE dalla UI (P26) | `select order_mode, order_mode_tetto from betfair_live_settings where id=1;` risponde |
| `tennis_bot_control_mode_2026-09-24.sql` | applicata (24/09) | colonna `tennis_bot_control.mode` (T1) | `select column_name from information_schema.columns where table_name='tennis_bot_control' and column_name='mode';` |
| `safe_request_modalita_manuale_2026-09-24.sql` | applicata (24/09) | barriera di `safe_request` per `strategy_modes.manual` | `select pg_get_functiondef('public.safe_request(text,jsonb)'::regprocedure) ilike '%v_atteso%';` |
| `pnl_betfair_reale_2026-09-24.sql` | applicata (24/09) | P&L reale del conto | da verificare con la RPC indicata nel file |
| `posizioni_chiuse_giornata`, `scalper_control_room`, `safe_request_approve_contesto`, `tennis_chiudi_bot`, `hazard_atlas` (24/09) | applicate 25/09 h10:15 | P28/P31/Z10 | firme sulle RPC (come fatto il 25/09) |
| `season_gaps_2026-09-25.sql`, `season_aggregates_2026-09-25.sql` | applicate 25/09 | catchup/referto buchi (Z9) | RPC `season_detail_gaps` risponde |
| `tennis_uscite_manuali_2026-09-25.sql` | **DA APPLICARE** (cronostoria h18:20) | auto-mode tennis + uscite tennis (P19-P21, Z12) | `select column_name from information_schema.columns where table_name in ('tennis_live_follow','tennis_bot_service_control','tennis_bot_control') and column_name in ('origine','uscite_automatiche');` → 3 righe |
| `uscite_automatiche_mike_2026-09-25.sql` | **DA APPLICARE** | kind `approva_uscita` (P30) | `select pg_get_functiondef('public.mike_request(text,jsonb)'::regprocedure) ilike '%approva_uscita%';` |
| `uscite_automatiche_scalper_2026-09-25.sql` poi `scalper_auto_mode_2026-09-25.sql` (in quest'ordine) | **DA APPLICARE** | interruttore globale scalper + uscite scalper (P22-P24, Z11) | `select * from scalper_service_control;` risponde (1 riga, id=1) |
| `omega_request_approve_contesto_2026-09-25.sql` | **DA APPLICARE** (facoltativa: senza, ripiego dichiarato su `p_id`) | prezzo visto nelle approvazioni Omega (P29) | firma `omega_request_approve(bigint,numeric,jsonb)` presente |
| `omega_transitions_catchup_2026-09-25.sql` (+ indice `idx_matches_fixture_date_settled` se manca) | **DA APPLICARE** + pubblicazione = decisione utente | transizioni Omega aggiornate (Z7) | `select public.omega_transitions_status();` |
| `safe_tennis_backmin_102_2026-09-25.sql` | **NECESSARIA** (cronostoria h20:40: sul DB `tennis.backMin`=1,01) | Safe tennis 1,02 (Q5) | `select params->'tennis'->>'backMin' from safe_strategy_control;` → `1.02` |
| `safe_base_banca_20_34_2026-09-25.sql` | facoltativa (il default del codice vale già) | pulizia `favLive*` | `select params->'base' from safe_strategy_control;` |
| `get_direction_eta_2026-09-25.sql`, `market_delays_ht_2026-09-25.sql` | da verificare in cronostoria (sessione B, audit 5: «DA APPLICARE (utente): 3 migrazioni + indice») | dashboard (fuori dai bot) | firme RPC |
| `uscite_manuali_default_2026-09-25.sql` | **DA APPLICARE PRIMA della fase 2** (aggiunta dal coordinatore, verificata sul codice: la migrazione esiste, non risulta ancora applicata) | porta a MANUALE il default delle uscite discrezionali di TUTTI i bot (Mike, Safe base/esatto/punta/tennis/model, scalper, i 4 bot tennis), decisione utente 25/09 sera, commit `890992f`; ADDITIVA e idempotente, aggiorna anche le righe GIA' scritte, non solo il default SQL | verifica dopo l'apply (dalla stessa migrazione, righe 133-138): `select id, params->'uscite_automatiche' from public.mike_control;`, `select id, params->'tennis_exit_approval', params->'uscite_automatiche' from public.safe_strategy_control;`, `select event_id, params->'uscite_automatiche' from public.scalper_control;`, `select bot_key, uscite_automatiche from public.tennis_bot_service_control;` → tutto `false` (Safe: mappa con le 5 strategie a `false`, `tennis_exit_approval=true`) |

**Criterio:** ogni riga «DA APPLICARE» è applicata o dichiarata «non applicata, il percorso X si salta». Un percorso
che dipende da una migrazione non applicata **non si testa** e si scrive nel referto (non si «prova lo stesso»).

### 1.2 `.env` del checkout principale: interruttori (solo NOMI e valore 0/1, nessun segreto)

Gli interruttori sono SPENTI se assenti (`Betfair/stream/canale_bot.py:1-60`, regola 5). Da leggere solo le righe
di questi nomi (es. `Select-String -Path .env -Pattern '^(NOME1|NOME2|...)='`), mai tutto il file.

| nome | atteso per il test | effetto | fonte |
|---|---|---|---|
| `LIVE_ORDER_MODE` | `LIVE` o `PAPER` (è il TETTO del runner calcio; la scelta vera è in UI) | tetto degli ordini del runner; `modo_ordini.modo_effettivo` = il più restrittivo | `Betfair/stream/modo_ordini.py:83-92`; `live_order_worker.py:141,167` |
| `TENNIS_LIVE_ORDER_MODE` | non nel `.env` → l'app passa `PAPER` | tetto del runner tennis | `desktop/main.js:250`; `tennis_runner.py:112-116` |
| `LIVE_KILL_SWITCH` | assente/`false` | freno d'ambiente | `trading/controls.py:107-140` |
| `SAFE_SCAN_CANALE` | 1 | scanner pubblica su 47336 | `safe_strategy/service.py:100` |
| `OMEGA_LEGGE_CANALE`, `MIKE_LEGGE_CANALE`, `SAFE_BOT_LEGGE_CANALE` | 1 | i bot leggono il feed dal canale 47336 | `omega_service.py:516`; `safe_strategy/canale_scan.py:63` |
| `OMEGA_CANALE_POSIZIONI`, `MIKE_CANALE_POSIZIONI`, `SAFE_CANALE_POSIZIONI`, `TENNIS_BOT_CANALE` | 1 | righe dei bot sul canale (47333-47335, 47337) | `canale_bot.py:130-137` |
| `SCALPER_CANALE` | 1 se si vuole Z11 dal canale (di serie SPENTO) | canale 47338 | `canale_bot.py:136`; referto `SCALPER_AUTO_MODE.md` §7 |
| `PUNTEGGI_CANALE`, `ESITI_ORDINI_CANALE` | 1 | punteggi e esiti terminali dal canale | `scores/scan_feed.py:102`; `esiti_ordini_canale.py` |
| `*_SVEGLIA_CANALE` (Omega/Mike/Safe/tennis bot) | 1 | sveglia dei bot dalla UI | AUDIT_TEMPO_REALE §1 |
| `MOTORE_ORDINI_CANALE`, `SAFE_ORDINI_VIA_CANALE`, `OMEGA_ORDINI_VIA_CANALE`, `SAFE_TENNIS_ORDINI_VIA_CANALE` | **assenti** (decisione D-1 dell'utente non presa: col canale i bot operano solo sulle partite seguite) | strada unica degli ordini | cronostoria 25/09 h19:20 |
| `MIKE_USE_FLUMINE_QUEUE` | **assente** (ramo coda di Mike rotto, M1) | — | `AUDIT_STRADE_ORDINE` §2.2 punto 2 |
| `HAZARD_ATLAS_SYNC` | 1 (messo dal coordinatore il 25/09 h13:05) | atlante a domanda + v4 | cronostoria 25/09 |
| `LIVE_TEMPI_ORDINE` | assente o 1 (acceso di serie) | righe `tempi_ordine` nel log (Z5) | `F0_TEMPI_ORDINE` §0 |
| `TENNIS_AUTO_MAX_PARTITE`, `SCALPER_AUTO_MAX_PARTITE` | assenti (default 5 e 2) | tetti auto-mode | `tennis_live/auto_mode.py`; `scalper/auto_mode.py:66-67,130` |

**Correzione (verificata sul codice di oggi):** la riga `MOTORE_ORDINI_CANALE` sopra descrive il DEFAULT di
baseline (assente). Per provare **§7.2** (auto-follow calcio + strada canale) serve un `.env` DIVERSO, acceso
apposta per quel blocco, PRIMA di avviare l'app:
`MOTORE_ORDINI_CANALE=1` (l'AUTO-FOLLOW stesso non nasce senza: è costruito DENTRO lo stesso `if` del motore,
`Betfair/stream/runner.py:1896-1903` — vedi §7.2), `SCALPER_CANALE=1` (per leggere Z11 dal canale 47338, come
già detto sopra), `LIVE_MARKET_TYPES` coi 13 nomi della whitelist committata (`Betfair/stream/config_stream.py:188-192
LIVE_MARKET_TYPES_PROPOSTA`, valore da riportare uguale nel `.env`: `MATCH_ODDS`, `CORRECT_SCORE`,
`HALF_TIME_SCORE`, `HALF_TIME`, `BOTH_TEAMS_TO_SCORE`, `OVER_UNDER_05`, `OVER_UNDER_15`, `OVER_UNDER_25`,
`OVER_UNDER_35`, `OVER_UNDER_45`, `OVER_UNDER_55`, `OVER_UNDER_65`, `OVER_UNDER_75` — riduce i mercati per evento,
decisione dell'utente non presa: la costante resta vuota finché non si decide, `config_stream.py:183-187`).
`SAFE_ORDINI_VIA_CANALE`/`OMEGA_ORDINI_VIA_CANALE` restano un gradino SUCCESSIVO (solo l'instradamento degli
ordini), non servono per far nascere l'auto-follow.

**Se non torna:** un interruttore di canale spento non rompe niente (il ripiego è il DB) ma la fase 2 misurerà la
fonte «db» invece di «canale»: va saputo PRIMA, non scoperto a video.

### 1.3 Build del frontend

- `cd frontend && npx tsc -p tsconfig.app.json --noEmit` → **0 errori** (regola del 17/09).
- `npm run build` (CLAUDE.md: dopo modifiche a `frontend/src`). L'app serve `frontend/dist` su 127.0.0.1:47330
  (`desktop/main.js:5,23`) e, se serve, ricompila da sé (`desktop/main.js:171`): la build va fatta PRIMA e a mano,
  per non far partire una build durante l'avvio.
- Controllo: la data di `frontend/dist/index.html` è successiva all'ultimo commit che tocca `frontend/src`
  (`git log -1 --format=%ci -- frontend/src`).

### 1.4 App spenta e bot fermi (fase 1)

- Nessun processo dell'app: `Get-Process electron, python -ErrorAction SilentlyContinue` → nessuno del repo
  (confrontare `Path`/riga di comando).
- Nessuna porta in ascolto: `Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 47330..47338` → vuoto.
- Sul DB (sola lettura) tutti i control `stopped` in `paper` (vedi fotografia §1.5).

### 1.5 Fotografia iniziale (sola lettura, da salvare in un file prima di qualunque clic)

```sql
select 'omega' as chi, to_jsonb(c) as riga from public.omega_control c
union all select 'mike', to_jsonb(c) from public.mike_control c
union all select 'safe', to_jsonb(c) from public.safe_strategy_control c
union all select 'tennis:'||c.bot_key, to_jsonb(c) from public.tennis_bot_service_control c
union all select 'scalper_servizio', to_jsonb(c) from public.scalper_service_control c   -- se la migrazione c'e'
union all select 'live_settings', to_jsonb(s) from public.betfair_live_settings s
order by 1;
-- righe per partita ancora attive (devono essere 0 con app spenta)
select 'tennis_bot_control' t, status, count(*) from public.tennis_bot_control group by status
union all select 'scalper_control', status, count(*) from public.scalper_control group by status;
-- code di comando non chiuse (devono essere 0 prima e dopo la fase 1)
select 'safe_strategy_requests' q, status, count(*) from public.safe_strategy_requests where status in ('proposed','pending','processing') group by status
union all select 'omega_manual_requests', status, count(*) from public.omega_manual_requests where status in ('proposed','pending','processing') group by status
union all select 'mike_requests', status, count(*) from public.mike_requests where status in ('pending','processing') group by status
union all select 'tennis_live_order_queue', status, count(*) from public.tennis_live_order_queue where status in ('pending','processing') group by status
union all select 'betfair_live_order_requests', status, count(*) from public.betfair_live_order_requests where status in ('pending','processing') group by status;
-- righe di follow tennis GIA' presenti PRIMA del test (aprire il Tennis Terminal ne scrive di nuove: vedi nota sotto)
select event_id, market_id, status, created_at from public.tennis_live_follow order by created_at desc;
```

**Nota (verificata sul codice):** aprire la pagina **Tennis Terminal** su una partita (`frontend/src/pages/TennisTerminal.tsx:112-116`,
`useEffect` che chiama `followTennisEvent(eventId, marketId)`) scrive SEMPRE, anche ad app spenta (è una RPC
Supabase diretta, non serve il runner), una riga in `tennis_live_follow` tramite la RPC `tennis_follow_event`
(`frontend/src/lib/tennis.ts:179-186`; RPC in `migrations/tennis_live.sql:189-256`, upsert su `event_id` con
`status='PENDING'`). La query sopra fotografa lo stato PRIMA: se durante la fase 1 (P19-P21, tennis) si apre il
Terminal per guardare una partita, quella riga (`event_id`) NON era nella fotografia e va cancellata esplicitamente
nel ripristino (§5.1), non solo confrontata col diff.

Colonne verificate sulle migrazioni: `omega_control`/`mike_control`/`safe_strategy_control` (id, status, mode,
params, stats, error, started_at, stopped_at, updated_at; Omega anche `daily_goal`), `tennis_bot_service_control`
(`tennis_bot_service_control_2026-09-17.sql:27-34`), `scalper_service_control` (`scalper_auto_mode_2026-09-25.sql:67-79`),
`betfair_live_settings` (`live_order_mode_control_2026-09-24.sql:31-44`). Gli stati delle code (`proposed`,
`processing`) li ho visti nelle RPC (`safe_request_approve_contesto_2026-09-24.sql`, `omega_request_approve_contesto_2026-09-25.sql`);
l'elenco completo dei CHECK di stato **da verificare** sullo schema.

### 1.6 Come si usa la UI ad app spenta — DECISIONE DELL'UTENTE (processo nuovo)

L'app desktop, avviandosi, lancia TUTTI i servizi (`desktop/main.js:288-333`): non esiste una modalità «solo UI».
Per la fase 1 serve servire `frontend/dist` senza servizi. Opzioni (serve il permesso dell'utente: è un processo):
- **A (proposta):** `cd frontend && npx vite preview --port 4173 --strictPort` (solo file statici; nessun bot, nessun
  runner). Login come proprietario (le RPC sono owner-only: `betfair_live_is_owner()` / `tennis_is_owner()`).
  I canali locali non ci sono: `svegliaBot` è best-effort e non solleva (`frontend/src/lib/localChannel.ts:338-344`);
  in console compariranno errori di connessione WebSocket a 47331-47338: attesi.
- **B:** nessuna UI in fase 1; si chiamano le RPC con il JWT del proprietario da uno script. **Sconsigliata:** non
  prova il cablaggio UI→RPC, che è metà dello scopo.

Da verificare con A: che il login Supabase funzioni dall'origine `http://localhost:4173` (password: nessun redirect).

### 1.7 La «sonda di lettura» dei servizi (da scrivere dalla sessione admin-26, NON da me)

Con i servizi spenti l'effetto nel servizio si prova chiamando **le stesse funzioni che il servizio usa per
rileggere**, in sola lettura, contro il DB vero. Nessuna `run_once`, nessuna `set_*`, nessun `log`. Proposta
(una riga per bot, `.venv\Scripts\python.exe -c "..."` dalla radice; da far rileggere al coordinatore prima dell'uso):

| sonda | funzioni (verificate) | stampa |
|---|---|---|
| S-OMEGA | `Betfair.omega.omega_db.read_control` (`omega_db.py:49`), `omega_config.resolve_params` (`omega_config.py:352`), `omega_proposte.modo_uscite` (`omega_proposte.py:250`) | status, mode, daily_goal, `modo_uscite`, `min_stake` |
| S-MIKE | `Betfair.mike.db.read_control` (`mike/db.py:59`), `mike.config.merge_params` (`mike/config.py:446`) | status, mode, `uscite_automatiche`, `stake` |
| S-SAFE | `Betfair.safe_strategy.bot_db.read_control` (`bot_db.py:62`), `bot_service.resolve_params` (`bot_service.py:296`), `normalize_variants` (`:483`), `modalita_di_strategia` (`:453`) per ognuna di `_STRATEGIES` (`:124`), `uscite_automatiche_di` (`:438`) per `STRATEGIE_CON_USCITE` (`:414`) | status, mode, varianti, modo per strategia (6), uscite per strategia (5) |
| S-TENNIS | `Betfair.stream.tennis_live.tennis_db.list_tennis_bot_services` (`tennis_db.py:525`), `tennis_bot_service.stato_desiderato` (`tennis_bot_service.py:336`) | per bot: acceso, mode, stake, uscite_automatiche |
| S-SCALPER | `Betfair.stream.scalper.scalper_service.Db().servizio()` (`scalper_service.py:89`) | status, mode, stake, strategia, params |
| S-ORDINI | `Betfair.stream.trading.controls.get_live_settings(force=True)` e `motivo_kill_switch()` (`controls.py:80,107`), `Betfair.stream.modo_ordini.descrivi(os.getenv('LIVE_ORDER_MODE'), order_mode)` (`modo_ordini.py:95`) | kill_switch, motivo, modo effettivo e perché |

**Da verificare prima dell'uso:** che l'import di `bot_service`, `tennis_bot_service`, `scalper_service` non avvii
thread né connessioni a livello di modulo (i thread partono nei `main()`: `bot_service.py:9526`,
`tennis_bot_service.py:903/949`, `scalper_service.py:643`); che `db_client.get_supabase_client` (usato da
`controls.get_live_settings`) legga le credenziali dal `.env` come i servizi. Memoria del 21/09: `load_dotenv` risale
al `.env` padre — la sonda è di SOLA LETTURA e va detto nel suo testo.

---

## 2. Ordine di esecuzione

1. §1 intero (migrazioni, `.env`, build, app spenta, fotografia). Esito scritto nel referto.
2. **Fase 1** nell'ordine P01 → P31 (§3). Ogni percorso: clic → SQL → sonda → ripristino del percorso → avanti.
   I percorsi che lasciano righe `stopping` le annotano; si ripristinano tutte insieme in §5.1.
3. §5.1 ripristino di fase 1 + diff con la fotografia (P32). **Fase 1 chiusa solo con diff vuoto** (a meno dei campi
   di tempo e `stats`, elencati in §5.1).
4. Referto di fase 1 all'utente. **Stop.** Si aspetta la sua indicazione.
5. Promemoria certificazione (§0.5) all'utente; sua decisione su replay prima o dopo.
6. **Fase 2** (§4) su indicazione: avvio dell'app da parte dell'utente → Z0 → Z1-Z3 → accensioni in paper una
   per volta (Z4) → Z5-Z14 → confronto DB finale.
7. §5.2 ripristino finale (bot fermi dall'utente, poi verifiche).

---

## 3. FASE 1 — percorsi UI → RPC → DB → servizio (APP SPENTA, BOT FERMI)

Formato di ogni percorso: **UI** (pagina, pulsante, `data-testid`, doppio consenso) · **Codice** (frontend) ·
**RPC** (nome e parametri veri) · **SQL** (migrazione che definisce la RPC) · **Riga attesa** · **Servizio** (chi
rilegge, e la sonda §1.7) · **In fase 2** (attività/log attesi quando il servizio gira) · **Ripristino** ·
**Superamento** · **Se non torna**.

Nota comune: tutte le RPC di comando sono SECURITY DEFINER owner-only; un errore «non autorizzato (owner-only)»
vuol dire login sbagliato, non un difetto del percorso.

### Omega

#### P01 — Omega: «avvia in prova» (Control Room)
- **UI:** Control Room → pannello bot → riga Omega → `avvia in prova` (`cr-avvia-paper-omega`,
  `frontend/src/components/controlroom/PannelloBot.tsx:816-822`). Nessuna conferma (prova).
- **Codice:** `frontend/src/lib/interruttori.ts:908 accendi` → `:860 avviaBot` (ramo Omega `:873-877`: pretende l'obiettivo
  del giorno e i params letti, altrimenti `ObiettivoOmegaIgnoto`/`ParametriOmegaIgnoti`) →
  `frontend/src/lib/omega.ts:1236-1244 activateOmega`.
- **RPC:** `omega_activate(p_mode='paper', p_daily_goal=<obiettivo a video>, p_params=<params correnti INTERI>)`.
- **SQL:** `migrations/omega_activate_conserva_params_2026-09-16.sql:40-74` (mode IN paper/live; `params =
  coalesce(p_params, params)`; `omega_snapshot_daily_goal`).
- **Riga attesa:** `omega_control` id=1: `status='running'`, `mode='paper'`, `daily_goal`=obiettivo, `params`
  **identici alla fotografia**, `error` NULL, `started_at`≈ora, `stopped_at` NULL.
  `select status, mode, daily_goal, params = '<params fotografati>'::jsonb as params_uguali from omega_control;`
- **Servizio:** `Betfair/omega/omega_service.py:7196 run_once` → `:7199 db.read_control()`; `status` e
  `omega_config.resolve_params` (`:7210`). Sonda S-OMEGA → `running paper`.
- **In fase 2:** il giro apre (la guardia d'avvio `:7208-7209` blocca solo finché il controllo d'avvio non è fatto).
- **Ripristino:** P03.
- **Superamento:** riga come sopra, `params_uguali = true`, la riga a video dice «prova».
- **Se non torna:** params cambiati = difetto 24 del catalogo (§7) riapparso; `mode` diverso = difetto 25.

#### P02 — Omega: «passa a soldi veri» con doppio consenso, poi «passa a prova»
- **UI:** riga Omega accesa → `passa a soldi veri` (`cr-a-live-omega`, `PannelloBot.tsx:798-805`) → compare
  `confermi? sono soldi veri` (`cr-conferma-live-omega`, `:787-796`, inerte per un istante: `troppoPresto`) → clic.
  Poi `passa a prova` (`cr-a-paper-omega`, `:779-786`).
- **Codice:** `interruttori.ts:924 cambiaModalita` → `:987 cambiaModalitaServizio` (ramo Omega) →
  `omega.ts:1252-1262 updateOmegaParams({mode})`.
- **RPC:** `omega_update_params(p_daily_goal=null, p_params=null, p_mode='live')`, poi `p_mode='paper'`.
- **SQL:** `migrations/omega_daily_v2.sql:89-122` (non tocca `status`; `mode = coalesce(p_mode, mode)`).
- **Riga attesa:** dopo il primo: `mode='live'`, `status` invariato (`running`), `params` invariati; dopo il
  secondo: `mode='paper'`.
- **Servizio:** `omega_service.py:1718` e `:2184` (`mode = control.get("mode","paper")`) al giro dopo. Sonda
  S-OMEGA fra i due clic → `running live`.
- **Controllo di sicurezza:** un SOLO clic su `passa a soldi veri` (senza conferma) NON deve scrivere niente
  (`select mode, updated_at from omega_control` invariati).
- **Ripristino:** il secondo clic stesso; verifica `mode='paper'`.
- **Se non torna:** una scrittura al primo clic = doppio consenso rotto (money-critical, fermare il test).

#### P03 — Omega: «ferma»
- **UI:** `ferma` (`cr-ferma-omega`, `PannelloBot.tsx:749-760`), il title dice «ferma le APERTURE».
- **Codice:** `interruttori.ts:916 spegni` → `:882 fermaBot` (ramo per nome, `else` finale = Omega) →
  `omega.ts:1246-1250 stopOmega`.
- **RPC/SQL:** `omega_stop()` — `migrations/omega_bot.sql:155-173`: `running → stopping`, altrimenti `stopped`.
- **Riga attesa:** `status='stopping'` (servizio spento: resta così), `mode` invariato.
- **Servizio:** `omega_service.py:7322-7323` porta `stopping → stopped` al primo giro (solo in fase 2).
- **Ripristino:** §5.1 (riga `stopping` → `stopped`).
- **Se non torna:** `stopped` scritto subito con un bot `running` = RPC diversa da quella del file (verificare
  quale versione è viva: `pg_get_functiondef`).

#### P04 — Omega: importo «stake minimo»
- **UI:** campo `stake minimo` della riga Omega (componente importo, `PannelloBot.tsx:866-930`), `salva`.
- **Codice:** `interruttori.ts:940 cambiaImporto` (ramo generico `:972-979`) → `scriviChiave(paramsLetti('omega'), 'min_stake', v)` →
  `updateOmegaParams({params: <INTERI>})`.
- **RPC/SQL:** `omega_update_params(p_params=<params interi con min_stake nuovo>)` — `omega_daily_v2.sql:89-122`.
- **Riga attesa:** `params` = fotografia con la sola chiave `min_stake` cambiata:
  `select (select jsonb_object_agg(k, v) from jsonb_each(params) e(k,v) where params->k is distinct from '<foto>'::jsonb->k) from omega_control;`
  → solo `min_stake`.
- **Servizio:** `omega_config.resolve_params` (S-OMEGA stampa `min_stake`).
- **Ripristino:** rimettere il valore di prima dallo stesso campo.
- **Se non torna:** altre chiavi sparite = «scrivere senza aver letto cancella» (`interruttori.ts:617-630`).

#### P05 — Omega: «uscite automatiche/manuali»
- **UI:** blocco uscite della riga (`cr-uscite-omega`, `cr-uscite-stato-omega`, pulsante `cr-uscite-cambia-omega`,
  `PannelloBot.tsx:686-714`): «passa ad automatiche» / «passa a manuali».
- **Codice:** `interruttori.ts:1022 cambiaUscite` → `paramsConUscite` (`:1149-1170`: `uscite_protezione =
  'automatico' | 'avvisa_e_proponi'`) → `updateOmegaParams({params})`.
- **RPC/SQL:** `omega_update_params(p_params=...)`.
- **Riga attesa:** `params->>'uscite_protezione'` = `automatico`, poi `avvisa_e_proponi`; nient'altro cambia.
- **Servizio:** `omega_proposte.py:250 modo_uscite`, usato da `process_proposte_uscita` (`:271`) nel giro
  (`omega_service.py:7248-7275`). Sonda S-OMEGA.
- **Ripristino:** tornare al valore della fotografia (default = `avvisa_e_proponi`, uscite manuali).
- **Se non torna:** la UI mostra «automatiche» con `params` diverso da `automatico` → lettura divergente
  (`statoUscite`, `interruttori.ts:1111-1128`).

#### P06 — Omega dalla pagina dedicata (secondo percorso, stesso servizio)
- **UI:** pagina Omega → attivazione (`frontend/src/pages/Omega.tsx:286`, `activateOmega(mode, goalInput,
  omegaParamsPatch(...))`) e interruttori della pagina (`Omega.tsx:370 creaInterruttori`).
- **Riga attesa / servizio / ripristino:** come P01-P03.
- **Scopo:** provare che la pagina e la Control Room scrivono la STESSA riga con gli stessi params (nessuna
  seconda verità). **Da verificare:** che `omegaParamsPatch` non tolga chiavi (diff come P04).

### Mike

#### P07 — Mike: «avvia in prova» e «avvia con soldi veri» (doppio consenso)
- **UI:** riga Mike → `avvia in prova` (`cr-avvia-paper-mike`) oppure `avvia con soldi veri` (`cr-avvia-live-mike`)
  → `confermi? ordini reali su Betfair` (`cr-conferma-avvio-live-mike`) (`PannelloBot.tsx:816-841`).
- **Codice:** `interruttori.ts:860 avviaBot` (ramo Mike, `:872`) → `frontend/src/lib/mike.ts:1889-1893 activateMike(mode)`
  (params **non passati**).
- **RPC:** `mike_activate(p_mode, p_params=null)`. **SQL:** `migrations/mike_bot.sql:183-203` (`params =
  coalesce(p_params, params)`: con null conserva).
- **Riga attesa:** `mike_control`: `status='running'`, `mode` scelto, `params` identici alla fotografia.
- **Servizio:** `Betfair/mike/service.py:2619 run_once` → `:2625 read_control` → `:2632 mode`; guardia d'avvio
  `:2638-2641`. Sonda S-MIKE.
- **Ripristino:** P09. In fase 1 provare il live SOLO se l'utente lo vuole (servizi spenti: nessun ordine può
  partire; all'avvio nuovo `ferma_al_nuovo_avvio` riporta comunque a paper, `service.py:2587-2616`).
- **Se non torna:** params diversi = RPC viva diversa dal file (in `mike_bot.sql` la `mike_activate` ha default
  `NULL`: verificare con `pg_get_functiondef`).

#### P08 — Mike: cambio modalità a caldo
- **UI:** `passa a soldi veri` + conferma / `passa a prova` (come P02, id `mike`).
- **Codice:** `interruttori.ts:987 cambiaModalitaServizio` (ramo Mike, `:1000-1002`) →
  `mike.ts:1901-1907 updateMikeParams(paramsLetti('mike'), modalita)`.
- **RPC/SQL:** `mike_update_params(p_params=<params letti INTERI>, p_mode)` — `mike_bot.sql:224-245`.
- **Riga attesa:** `mode` cambiato, `status` invariato, `params` identici (li riscrive uguali).
- **Servizio:** `service.py:2632`. Sonda S-MIKE.
- **Se non torna:** `ParametriNonLetti` a video = lo stato non era caricato (atteso, non un difetto).

#### P09 — Mike: «ferma»
- **UI:** `cr-ferma-mike`. **Codice:** `interruttori.ts:882 fermaBot` → `mike.ts:1895-1899 stopMike`.
- **RPC/SQL:** `mike_stop()` — `mike_bot.sql:205-222` (`running → stopping`).
- **Servizio (fase 2):** `service.py:2846-2848` (`stopping → stopped`). **Ripristino:** §5.1.

#### P10 — Mike: uscite automatiche/manuali
- **UI:** `cr-uscite-cambia-mike` (e la scheda parametri `MikeParamsSheet`, gruppo «uscite»).
- **Codice:** `interruttori.ts:1022 cambiaUscite` → `paramsConUscite` (`uscite_automatiche: bool`) →
  `updateMikeParams(params)`.
- **Riga attesa:** `params->'uscite_automatiche'` = `false` poi `true`; il resto invariato.
- **Servizio:** `Betfair/mike/engine.py:2282 gate_uscite` (ultima parola di `decide`), costanti `:2194-2209`.
  Sonda S-MIKE (`merge_params` → `uscite_automatiche`).
- **Ripristino:** valore della fotografia. **Corretto:** il default NON è più `true` — decisione utente 25/09 sera
  (commit `890992f`, migrazione `uscite_manuali_default_2026-09-25.sql`, §1.1): il default applicativo e quello
  scritto sul DB sono ora `false` (uscite manuali) per Mike come per tutti i bot.

### Safe (base / esatto / punta / tennis / modello / a mano)

Regola da provare in tutti: **`variants` e `strategy_modes` si scrivono SEMPRE interi** (`interruttori.ts:24-36`,
`paramsAccensioni` `:353-388`), `strategy_modes` con TUTTE e sei le chiavi (`STRATEGIE_SAFE_TUTTE`, `:69`).
Controllo SQL comune dopo ogni clic:
```sql
select status, mode, params->'variants' as varianti, params->'strategy_modes' as modi,
       params->'uscite_automatiche' as uscite, params->'stake'->'per_strategia' as stake
  from public.safe_strategy_control;
```

#### P11 — Safe base: «avvia in prova» a servizio fermo
- **UI:** riga «Safe base» → `avvia in prova` (`cr-avvia-paper-safe-base`).
- **Codice:** `interruttori.ts:908 accendi` → `:818 conCambio` (lettura FRESCA dal DB,
  `components/controlroom/comandiBot.ts:47-73 rileggiSafeDalDatabase`) → `:776 scriviSafe` → servizio fermo →
  `activateSafe(voluta, params)` (`frontend/src/lib/safeBot.ts:1079-1085`).
- **RPC:** `safe_activate(p_mode='paper', p_params=<params INTERI: variants=['base'], strategy_modes con 6 chiavi>)`.
- **SQL:** `migrations/safe_strategy_bot.sql:171-199`.
- **Riga attesa:** `status='running'`, `mode='paper'`, `variants=["base"]`, `strategy_modes` = base/esatto/punta/
  tennis/model/manual tutti `paper` (model/manual CONSERVATI dal valore di prima, `'conserva'`), resto dei params
  identico alla fotografia.
- **Servizio:** `Betfair/safe_strategy/bot_service.py:8839 run_once` → `:8856 read_control` → `:8878-8884
  resolve_params`; per strategia `modalita_di_strategia` (`:453-481`: tetto del servizio + voce scritta; assente =
  paper). Sonda S-SAFE.
- **Ripristino:** P14.

#### P12 — Safe esatto acceso SUBITO dopo base (reperto A del 18/09: due clic ravvicinati)
- **UI:** con base acceso, `avvia in prova` su «Safe esatto» entro 1-2 s dal clic precedente.
- **Codice:** `conCambio` rilegge dal DB (`interruttori.ts:739-755 statoSafeFresco` con `rileggiSafe`), servizio
  già in corsa nella stessa modalità → `updateSafeParams(params)` (`safeBot.ts:1093-1097`).
- **RPC/SQL:** `safe_update_params(p_params=<interi>)` — `safe_strategy_bot.sql:227-245`.
- **Riga attesa:** `variants=["base","esatto"]` (base NON sparito), `started_at` invariato.
- **Se non torna:** base sparito = reperto A riapparso (la rilettura fresca non è agganciata in Control Room).

#### P13 — Safe punta a soldi veri (tetto che sale)
- **UI:** riga «Safe punta» accesa in prova → `passa a soldi veri` → conferma.
- **Codice:** `interruttori.ts:924 cambiaModalita` → `conCambio('punta','live')` → `scriviSafe(..., {puoAccendere:false})`
  → tetto voluto `live` ≠ `paper` → `activateSafe('live', params)`.
- **Riga attesa:** `mode='live'` (tetto), `strategy_modes.punta='live'`, base/esatto `paper`, tennis/model/manual
  invariati, `status` resta `running`.
- **Servizio:** `modalita_di_strategia('punta','live',params)='live'`, `('base','live',params)='paper'`. Sonda S-SAFE.
- **Poi:** `passa a prova` su punta → `strategy_modes.punta='paper'`, tetto torna `paper` (nessun'altra voce live).
- **Se non torna:** tetto rimasto `live` senza voci live, o base diventata live = modalità ereditata (difetto 25).

#### P14 — Safe: spegnere l'ultima strategia accesa
- **UI:** `ferma` sulle righe accese, l'ultima per ultima.
- **Codice:** `scriviSafe` con `nessunaAccesa(acc)` → `stopSafe()` (`safeBot.ts:1087-1091`), MAI `variants: []`
  (`interruttori.ts:760-775`: la lista vuota vuol dire «tutte accese»).
- **RPC/SQL:** `safe_stop()` — versione viva `migrations/safe_strategy_paper_live_2026-09-13.sql:634-655`
  (`running → stopping` **e `mode='paper'`**).
- **Riga attesa:** `status='stopping'`, `mode='paper'`, `variants` = l'ultima scrittura prima dello stop (non vuota).
- **Servizio (fase 2):** `bot_service.py:9003-9005` (`stopping → stopped`).
- **Se non torna:** `variants=[]` sul DB = alla riaccensione partirebbero TUTTE (fermare il test).

#### P15 — Safe tennis dalla scheda tennis («solo tennis»)
- **UI:** Control Room, scheda **tennis** → «Safe tennis» → `avvia in prova` (il pannello dichiara prima del clic
  le differenze «solo tennis»).
- **Codice:** `comandiBot.ts:100-137 creaComandiControlRoom` (sport `tennis`) → `soloTennis` → `scriviAccensioni(
  accensioniSoloTennis(modalita), {altre:'prova', extra: extraSoloTennis})` (`components/controlroom/soloTennis.ts`).
- **Riga attesa:** `variants=["tennis"]`, `strategy_modes`: tennis `paper`, base/esatto/punta `paper`, **model e
  manual portati a `paper`** (`altre:'prova'`); stake tennis 3 € e entrate automatiche come da `extraSoloTennis`
  (**chiavi esatte da verificare** in `soloTennis.ts`).
- **Controllo calcio/tennis distinti:** nessuna strategia calcio resta accesa; il gesto lo dichiara per nome.
- **Poi `passa a prova` dal live**: solo la modalità del tennis cambia, stake ed entrate NON si toccano
  (`comandiBot.ts:127-135`).

#### P16 — Safe «modello» e «a mano» (solo modalità)
- **UI:** righe `Safe modello` / `Safe a mano` (id `safe-model`, `safe-manual`, `interruttori.ts:188-199`).
- **Codice:** `accendi`/`cambiaModalita` → `:835 scriviSoloModalita`: a servizio FERMO rifiuta
  (`SafeFermoPerStrumento`); con servizio in corsa scrive SOLO la sua voce di `strategy_modes`; `spegni` rifiuta
  (`StrumentoSenzaSpegnimento`, `:919`).
- **Casi:** (a) servizio fermo → errore a video, **nessuna scrittura** (`updated_at` invariato); (b) servizio acceso
  (P11) → `strategy_modes.model='live'` con doppio consenso → tetto `live` via `safe_activate('live', params)`;
  base resta `paper`; (c) ritorno a prova.
- **Servizio:** `modalita_di_strategia('model', mode, params)`; per `manual` anche la barriera SQL di `safe_request`
  (`migrations/safe_request_modalita_manuale_2026-09-24.sql:29-60`, `v_atteso`).

#### P17 — Safe: uscite per strategia
- **UI:** `cr-uscite-cambia-safe-base` (e per esatto/punta/tennis/model; «a mano» non ha il blocco).
- **Codice:** `interruttori.ts:1022` → `paramsConUscite` (`:1159-1168`: mappa `uscite_automatiche.{strategia}`;
  per tennis anche `tennis_exit_approval = !automatiche`) → `updateSafeParams(params)` da lettura fresca.
- **Riga attesa:** `params->'uscite_automatiche'->>'base'='false'`; per tennis anche `params->>'tennis_exit_approval'='true'`.
- **Servizio:** `bot_service.py:417 normalize_uscite_automatiche`, `:438 uscite_automatiche_di`, cancello nel giro
  `:3800`. Sonda S-SAFE.
- **Ripristino:** valori della fotografia.

#### P18 — Safe: stake per strategia
- **UI:** campi `stake base/esatto/punta/tennis` (chiavi `stake.per_strategia.<x>`, ripiego `stake.laySize`/`backSize`,
  `interruttori.ts:167-203`).
- **Codice:** `interruttori.ts:963-970` (lettura fresca → `scriviChiave` → `updateSafeParams`).
- **Riga attesa:** solo `params->'stake'->'per_strategia'->'<x>'` cambiato.
- **Ripristino:** valore di prima.

### I 4 bot tennis (scalper / pro / flb / swing)

#### P19 — Interruttore di servizio: avvia, cambia modalità, stake, ferma
- **UI:** righe «Scalper tennis», «Pro tennis», «FLB tennis», «Swing tennis» (scheda tennis; id = bot key,
  `interruttori.ts:212-218`).
- **Codice e RPC:**
  - avvia: `interruttori.ts:860 avviaBot` (`:868-871`) → `frontend/src/lib/tennis.ts:945-955
    activateTennisBotService(bot, mode)` → `tennis_bot_service_activate(p_bot_key, p_mode, p_stake=null, p_params=null)`;
  - cambia modalità: `:987` (`:993-996`) → `tennis.ts:970-983 updateTennisBotService({mode})` →
    `tennis_bot_service_update_params(p_bot_key, p_mode, null, null)` (NON tocca `status`);
  - stake: `:953-961` → `update_params(p_stake)`;
  - ferma: `:882-884` → `tennis.ts:959-963` → `tennis_bot_service_stop(p_bot_key)`.
- **SQL:** `migrations/tennis_bot_service_control_2026-09-17.sql:49-76` (activate: mode OBBLIGATORIA, params
  conservati), `:78-95` (stop → `stopping`), `:131-160` (update senza `status`).
- **Riga attesa:** `tennis_bot_service_control` del SOLO bot cliccato: `status='running'`/`mode` scelto; gli altri
  tre invariati. Dopo ferma: `status='stopping'`, `stopped_at`≈ora.
- **Servizio:** `Betfair/stream/tennis_live/tennis_bot_service.py:402 riconcilia_interruttori` (legge
  `list_tennis_bot_services`, `stato_desiderato` `:336-362`). Sonda S-TENNIS.
- **Ripristino:** ferma → §5.1. **Nota (corretta, R2 chiuso da `6ac2543`):** a un avvio nuovo il ponte riporta a
  `stopped` SIA lo `status` SIA la `mode='paper'` (`tennis_bot_service.py:806-855 ferma_interruttori_al_nuovo_avvio`,
  riga 847-848: `db.set_tennis_bot_service_state(bot, status="stopped", stopped=True, stats=stats, mode="paper")`),
  come Omega/Mike/Safe (`avvio_app.py:212-220`). **Reperto R2 chiuso**, non più aperto (§9 aggiornato): la versione
  precedente di questa riga diceva «SOLO lo `status`, NON la `mode`» — era vera prima del commit `6ac2543` (25/09
  sera), non più oggi. La riga da controllare in fase 2 (Z0.2) è che una riga rimasta `stopping` da PRIMA del fix
  (residuo del 24/09) venga effettivamente ripresa al prossimo avvio nuovo: vedi Z0.2.

#### P20 — Tennis: uscite automatiche/manuali per bot
- **UI:** componente `UsciteTennis` montato nella riga dei 4 bot (`frontend/src/pages/ControlRoom.tsx:458`,
  `components/controlroom/UsciteTennis.tsx:54`): «uscite: automatiche» → conferma → manuali; ritorno senza conferma.
- **RPC/SQL:** `tennis_bot_service_set_uscite(p_bot_key, p_automatiche)` (`tennis.ts:914-924`) —
  `migrations/tennis_uscite_manuali_2026-09-25.sql:75-103` (non tocca status/mode/stake/params).
- **Riga attesa:** `tennis_bot_service_control.uscite_automatiche=false` sul bot; nient'altro.
- **Servizio:** `stato_desiderato` (campo `uscite_automatiche`), `_propaga_uscite` (`tennis_bot_service.py:741`) →
  runner `_aggiorna_uscite` (`tennis_runner.py:1535`). Lo scalper tennis resta «sempre automatiche» (referto
  `TENNIS_AUTO_MODE.md` §3).
- **Dipende da:** migrazione `tennis_uscite_manuali` (senza: nessun interruttore in UI, detto a video).

#### P21 — Tennis per partita: «arma» dal pannello della partita
- **UI:** scheda della partita tennis → `TennisBotPanel` (`frontend/src/components/tennis/TennisBotPanel.tsx`):
  checkbox dry-run (default `orderMode !== 'PAPER'`, `:117`), `handleArm` (`:498-535`) con UN `window.confirm`
  solo se `!dryRun && orderMode==='LIVE'` (`:506-515`).
- **RPC:** `tennis_bot_arm(p_event_id, p_bot_key, p_dry_run, p_stake, p_params)` (`tennis.ts:821-837`); disarmo
  `tennis_bot_disarm` (`tennis.ts:840-847`).
- **SQL:** versione viva `migrations/tennis_bot_control_mode_2026-09-24.sql:56-131`: **scrive SEMPRE
  `mode='paper'`** (anche su riarmo), guardia anti re-arm.
- **Riga attesa:** `tennis_bot_control(event_id, bot_key)`: `status='requested'`, `mode='paper'`, `dry_run` come la
  checkbox, `stake`, `params`.
- **Controllo chiave:** con la checkbox tolta e la conferma «ORDINI REALI» accettata, la riga nasce comunque
  `mode='paper'` → il runner simula (`guardie_tennis.py:75-106 modalita_riga/modalita_esecuzione_bot`).
  **Reperto da portare all'utente:** il testo del confirm dice «ordini reali», la riga dice paper. Il live per
  partita richiede una RPC con `p_mode` (decisione T1 non presa, commento della migrazione `:18-23`).
- **Servizio:** runner tennis `bot_control_worker` (`tennis_runner.py:1302`), non attivo in fase 1.
- **Serve:** un `event_id` tennis vero (una partita del feed). Con app spenta nessun runner la prende: la riga
  resta `requested`.
- **Ripristino:** `tennis_bot_disarm`, poi §5.1 (righe `requested/stopping` → `stopped`).

### Scalper calcio

#### P22 — Interruttore globale: avvia in prova, rifiuto del live a caldo, stake, ferma
- **UI:** riga «Scalper calcio» (`interruttori.ts:155-167`; nota `modalitaSoloAllAvvio` a video
  `cr-modalita-all-avvio-scalper`, `PannelloBot.tsx:771-777`).
- **Codice e RPC:**
  - avvia: `interruttori.ts:860-864` → `frontend/src/lib/scalperControlRoom.ts:165 attivaScalperAuto` →
    `scalper_auto_activate(p_mode)`;
  - cambio modalità: `interruttori.ts:927` e `:988` lanciano `ScalperModalitaAllAvvio` (nessuna RPC);
  - stake: `:943-947` → `scalperControlRoom.ts:185 aggiornaScalperAuto` → `scalper_auto_update(p_stake)`;
  - ferma: `:885-898` → `scalperControlRoom.ts:176 fermaScalperAuto` → `scalper_auto_stop()` (ripiego sessione per
    sessione se la RPC manca).
- **SQL:** `migrations/scalper_auto_mode_2026-09-25.sql:99-154` (activate: rifiuta se già acceso nell'altra
  modalità), `:162-192` (stop: servizio `stopped` + sessioni attive → `stopping`/`stopped`), `:199-234` (update).
- **Riga attesa:** `scalper_service_control`: `status='running'`, `mode='paper'`; stake cambiato solo nella colonna;
  dopo ferma `status='stopped'`, `sessioni_fermate`=0 (nessuna sessione con app spenta).
- **Caso negativo (paper e live mai insieme):** con l'interruttore `running/paper` chiamare l'avvio live (se la UI
  lo permette) → eccezione «scalper gia' acceso in paper…», **nessuna scrittura**.
- **Servizio:** `Betfair/stream/scalper/scalper_service.py:330 giro_auto` (rilegge l'interruttore ogni 3 s,
  feed ogni 15 s `:61`). Sonda S-SCALPER.
- **Dipende da:** migrazioni scalper del 25/09.

#### P23 — Scalper: uscite automatiche/manuali
- **UI:** `cr-uscite-cambia-scalper`. **Codice:** `interruttori.ts:1025-1028` → `scalperControlRoom.ts:294
  impostaUsciteScalper` → `scalper_uscite_automatiche(p_automatiche)`.
- **SQL:** `scalper_auto_mode_2026-09-25.sql:239-270` (sessioni attive + riga dell'interruttore).
- **Riga attesa:** `scalper_service_control.params->'uscite_automatiche'`; ritorno `0` sessioni con app spenta.
- **Servizio (fase 2):** `scalper_session.py:473 applica_uscite_automatiche`, `:517 control_stato_e_params`.

#### P24 — Scalper: card per partita (facoltativo in fase 1)
- **UI:** `components/live/ScalperPanel.tsx:167` (e `components/omega/MissionCard.tsx:314`) →
  `frontend/src/lib/scalper.ts:141-153 activateScalper` → `scalper_activate(p_event_id, p_mode, p_dry_run, p_stake, p_params)`.
- **SQL:** `scalper_auto_mode_2026-09-25.sql:277-339`: pretende `live_follow` dell'evento, scrive `origine='manuale'`.
- **In fase 1 si prova SOLO il rifiuto** (evento non seguito → «evento non seguito: … (segui prima la partita)»,
  nessuna riga). Il caso positivo richiede un follow: si fa in fase 2.

### Comandi trasversali

#### P25 — «FERMA TUTTI»
- **Preparazione:** accendere in prova (P01, P07, P11, P19 su un bot, P22).
- **UI:** `cr-ferma-tutti` (`PannelloBot.tsx:340-345`), **nessuna conferma** (regola 2 del pannello, `:26-28`).
- **Codice:** `PannelloBot.tsx:306-325 fermaTutti`: per ogni bot acceso, in sequenza, `comandi.fermaBot`; li prova
  TUTTI anche se uno fallisce; i falliti a video (`cr-non-fermati`, `:452`).
- **Righe attese:** Omega/Mike/Safe `stopping` (Safe anche `mode='paper'`), tennis del bot acceso `stopping`,
  scalper interruttore `stopped`.
- **Caso d'errore voluto (facoltativo):** nessuno praticabile senza toccare il DB; si verifica solo che il ciclo non
  si interrompa (test di componente esistente: `PannelloBot.test.tsx`).
- **Ripristino:** §5.1.

#### P26 — «Ordini reali: OFF / PAPER / LIVE» (ex `LIVE_ORDER_MODE` del `.env`)
- **UI:** riga `cr-ordini-reali` in testa al pannello (`frontend/src/pages/ControlRoom.tsx:602`,
  `components/controlroom/RigaOrdiniReali.tsx:168-275`): `off` (`cr-ordini-reali-off`), `paper`
  (`cr-ordini-reali-paper`), `live` (`cr-ordini-reali-live`) → `confermi? ordini reali su Betfair`
  (`cr-ordini-reali-conferma-live`). LIVE disabilitato se il tetto dichiarato dal runner non lo consente
  (`liveConsentito`, title `:262-264`).
- **Codice:** `interruttori.ts:1293 scegliModoOrdini` → `frontend/src/lib/liveOrders.ts:692-697 setLiveOrderMode`.
- **RPC/SQL:** `set_live_order_mode(p_mode)` — `migrations/live_order_mode_control_2026-09-24.sql:68-96` (scrive
  SOLO le colonne del modo: `order_mode`, `order_mode_updated_at`, `order_mode_updated_by`).
- **Riga attesa:** `select order_mode, order_mode_updated_by, order_mode_updated_at, kill_switch, order_mode_tetto from betfair_live_settings;`
  → `order_mode` come il clic, `updated_by` = email del proprietario, `kill_switch` INVARIATO.
- **Servizio:** runner calcio `live_order_worker.py:485 _refresh_settings` → `modo_ordini.registra_settings`;
  aperture governate da `:167 _live_order_mode` e `:183 _blocco_apertura_modo` (le chiusure passano sempre, `:112`);
  bot sul REST live: `safe_strategy/execution.py:91-131 _live_brake`. Sonda S-ORDINI: `descrivi(env, db)` →
  effettivo = min(tetto `.env`, scelta).
- **Casi:** OFF → PAPER → (LIVE con doppio consenso, solo se l'utente lo vuole in fase 1; con runner spento nessun
  ordine) → **PAPER** finale.
- **Ripristino:** `paper` (lo stato con cui nasce la colonna e a cui scende a ogni avvio nuovo,
  `live_order_mode_avvio` `:108-160`).
- **Se non torna:** `kill_switch` cambiato = la RPC viva non è quella del file.

#### P27 — Kill-switch / freno unico (R3, commit `6ac2543`)
- **UI:** DUE punti, stessa RPC. (a) pagina Segui Live → `LiveControlsPanel` (`frontend/src/pages/SeguiLive.tsx:857`,
  `components/live/LiveControlsPanel.tsx:137-160`): attivazione SENZA conferma, disattivazione con `window.confirm`;
  scorciatoia `Esc` in Segui Live (`SeguiLive.tsx:451-460,476`, con `window.confirm` in attivazione). (b) **Corretto
  (reperto chiuso, non più aperto come nella versione precedente di questa riga):** ORA c'è anche una riga in
  Control Room, accanto a «Ordini reali» — `frontend/src/components/controlroom/RigaFreno.tsx`
  (`data-testid="cr-freno"`, stato `cr-freno-stato`, fonte `cr-freno-fonte`, età `cr-freno-quando`): `cr-freno-tira`
  = TIRA IL FRENO, un clic, nessuna domanda (come «FERMA TUTTI»); `cr-freno-rilascia` → doppia conferma
  (`cr-freno-conferma-1`, `cr-freno-conferma-2`) per rialzarlo — mai automatico.
- **Codice/RPC:** `liveOrders.ts:683-688 setKillSwitch` → `set_live_kill_switch(p_on)` —
  `migrations/betfair_live_controls.sql:85-110`.
- **Riga attesa:** `betfair_live_settings.kill_switch=true`, poi `false`; `order_mode` INVARIATO.
- **Servizio:** `trading/controls.py:107 motivo_kill_switch` (env + DB, cache 2 s) → S-ORDINI stampa
  `db_kill_switch_attivo`; worker `live_order_worker.py:3576-3580` (ciclo), `:3622-3633` (per riga: apertura
  rifiutata, chiusura servita), canale `:3346-3349`; tennis `guardie_tennis.py:236,281-294`. **Corretto:** con
  `6ac2543` il freno tirato ferma ANCHE Mike (`execution._freno_aperture`, `_freno_resting_paper`) e lo scalper
  calcio (`scalper_service.py:613-619 freno_supervisore`/`scalper_session.motivo_freno`), non più solo
  runner/tennis come nella versione precedente di questa riga (vedi Z13.4).
- **Ripristino:** rilasciare da entrambi i punti UI porta alla stessa riga: verificare `kill_switch=false` una
  volta sola (confermando il dialogo).

#### P28 — Richieste manuali Safe (`safe_request_*`)
- **In fase 1 solo il contratto, senza righe nuove** (con bot fermi non esistono proposte vere, e una riga
  `pending` lasciata sul DB verrebbe presa al primo giro della fase 2):
  - `safe_request_approve(p_id=<id inesistente>)` → eccezione «richiesta N inesistente»
    (`migrations/safe_request_approve_contesto_2026-09-24.sql:28-90`);
  - `safe_request_approve(p_id=<una proposta già chiusa>)` → `{ok:false, note:'la proposta non è più in attesa…'}`,
    e la UI lo mostra come errore (`frontend/src/lib/controlRoomProposte.ts:365-378 esigiOk`);
  - `safe_request('kind_inventato', …)` → «kind non valido» (`safe_request_modalita_manuale_2026-09-24.sql:50-52`).
- **Caso positivo (fase 2, Z4-Safe):** proposta vera `proposed` → clic «piazza»/«approva» sulla scheda
  (`SchedaPropostaOpportunita`/`SchedaChiusura`) → `useControlRoom.ts:2749-2776 piazzaOpportunita` /
  `:2824-2856 approva` → `safe_request_approve(p_id, p_price, p_legs_prices, p_slippage_pct, p_contesto)`
  (`safeBot.ts:1296-1320`). Riga attesa `safe_strategy_requests`: `status='pending'`, `payload` = payload di
  prima + `approved_at`, `price_visto`, `price_visto_at`, `prezzo_visto_ctx`. Servizio: `bot_service.py:2330
  process_requests` → `:2563 _request_place` (tolleranza sul prezzo visto `:2673-2720`; `meta.prezzo_visto_ctx`
  `:2776-2777`). Esito a video dalla striscia B17 (`AUDIT_2026-09-25/SCHEDE_ABBINAMENTO_PREZZO.md` §2).

#### P29 — Richieste manuali Omega (`omega_request_approve` con contesto e prezzo visto)
- **Fase 1:** solo contratto: id inesistente → eccezione; proposta non `proposed` → `ok:false`
  (`migrations/omega_request_approve_contesto_2026-09-25.sql:33-88`).
- **Fase 2:** proposta d'uscita Omega vera → `SchedaChiusuraOmega` → `useControlRoom.ts:2879-2895 approvaOmega` →
  `frontend/src/lib/omegaProposte.ts:320-340` → `omega_request_approve(p_id, p_price, p_contesto)`. Riga attesa
  `omega_manual_requests`: `status='pending'`, payload + `approved_at`, `price_visto`, `price_visto_at`,
  `prezzo_visto_ctx` (con `prezzo_segnale`). Servizio: `omega_service.py:4843 process_manual` →
  `:5394 _manual_cashout` (esegue ancora a mercato: B17 aperto). Senza la migrazione: ripiego dichiarato
  «prezzo visto non salvato».

#### P30 — Mike «approva uscita»
- **Fase 1 (contratto):** `mike_request('approva_uscita', {event_id: 'x'})` senza `chiave` → eccezione
  «approva_uscita senza chiave della proposta» (`migrations/uscite_automatiche_mike_2026-09-25.sql:42-67`);
  `mike_request('cashout', {})` → «payload senza event_id». Nessuna riga.
- **Fase 2:** con uscite manuali (P10) e una proposta viva in `mike_events.ctx.uscita_proposta`:
  `PropostaUscitaMike.tsx:97-107` → `requestMike('approva_uscita', {event_id, bot, mode, chiave, contesto})` →
  riga `mike_requests` `kind='approva_uscita'`; servizio `service.py:2374-2375` → `:2435 _request_approva_uscita`
  (chiave diversa → `rejected/proposta_cambiata`).

#### P31 — Tennis «Chiudi» di un bot (`chiudi_bot`)
- **Fase 1 (contratto, già provato il 25/09 h10:15):** `request_tennis_live_order({action:'chiudi_bot', ...})`
  con `bot` non valido → «bot non valido per chiudi_bot»; senza `event_id`/`market_id` → eccezioni
  (`migrations/tennis_chiudi_bot_2026-09-24.sql:28-116`). Nessuna riga.
- **Fase 2:** «Chiudi» della riga di un bot tennis in posizione paper → `components/controlroom/chiudiRiga.ts`
  → `tennis.ts:466-477 requestTennisChiudiBot` → riga `tennis_live_order_queue` (payload con `action='chiudi_bot'`,
  `bot`, `event_id`, `market_id`, `mode='paper'`); servizio `tennis_live_order_worker.py` →
  `chiusura_manuale.py:245 gestisci_riga` (`:163 richiesta_ambigua` fail-closed).

#### P32 — Chiusura della fase 1: diff con la fotografia
- Rilanciare le query di §1.5. **Superamento:** stesse righe e stessi valori di `status`, `mode`, `params`,
  `daily_goal`, `stake`, `uscite_automatiche`, `order_mode`, `kill_switch`; differenze ammesse SOLO in
  `updated_at`, `started_at`, `stopped_at`, `error` (NULL), `order_mode_updated_at/by`. Code: zero righe
  `proposed/pending/processing` in più.

**Totale fase 1: 32 percorsi (P01-P32).**

---

## 4. FASE 2 — ACCENSIONE IN PAPER (solo su indicazione dell'utente)

Premessa: l'utente avvia l'app. Tutto in PAPER. «Ordini reali» su PAPER. Nessun dry-run tolto. Il coordinatore
confronta a video e sul DB (sola lettura). Le accensioni si fanno **una per volta**, e dopo ogni accensione si
esegue il blocco del bot (Z4) prima della successiva.

### Z0 — All'avvio nessun bot opera

| # | cosa fa ora | cosa ci aspettiamo | come si verifica | se non torna |
|---|---|---|---|---|
| Z0.1 | `avvio_app.ferma_al_nuovo_avvio` (`Betfair/stream/avvio_app.py:151-254`) a ogni avvio NUOVO (`APP_BOOT_ID` nuovo, `desktop/main.js:42,230`) scrive `status='stopped'`, `mode='paper'`, timbra `stats.boot_id` | Omega/Mike/Safe `stopped`+`paper`; Safe tutte le `strategy_modes` a `paper` (`bot_service.py:8755 strategy_modes_a_paper`); attività `avvio_app_bot_fermato` SOLO se c'era qualcosa da fermare | query §1.5 dopo 60 s dall'avvio; `select ts, kind, payload from omega_activity where kind='avvio_app_bot_fermato' order by ts desc limit 3;` (idem `safe_strategy_activity`, `mike_activity`) | un bot `running` senza clic = difetto 22 del catalogo: **FERMA TUTTI e stop del test** |
| Z0.2 | tennis: `ripresa_ponte` (**corretto**: `tennis_bot_service.py:862-881`, non `:849-868`) chiama `ferma_bot_al_nuovo_avvio` (righe per partita) POI `ferma_interruttori_al_nuovo_avvio` (`:806-855`, interruttori) di un avvio vecchio; runner tennis `guardie_tennis.py:317 ripresa_all_avvio` | tutti i `tennis_bot_service_control` `status='stopped'` **E `mode='paper'`** per i 4 bot (fix R2, `6ac2543`, non più «mode invariata» come diceva P19 in precedenza); nessuna `tennis_bot_control` attiva | query §1.5 | righe attive = guardia del ponte non riuscita (log `[tennis-bot-svc] controllo d'avvio del ponte NON riuscito`) |
| Z0.2bis | **[coordinatore, verifica aggiunta]** una riga `tennis_bot_service_control` rimasta `status='stopping'` da PRIMA del fix R2 (residuo noto sul DB del 24/09, non ancora passato da un avvio nuovo con `6ac2543` in produzione) | dopo un avvio NUOVO dell'app (boot_id diverso, non un riavvio del watchdog: `ferma_interruttori_al_nuovo_avvio` salta se `AA.stesso_avvio(r.get("stats"), boot)`, `:839-840`) | `select bot_key, status, mode from tennis_bot_service_control;` → tutti e 4 `status='stopped'`, `mode='paper'` | coerente | un bot ancora `status='stopping'` dopo l'avvio nuovo = KO del fix R2 (`6ac2543`): il residuo del 24/09 non è stato ripreso, `acceso = status in ('running','stopping')` a `:833` non l'ha intercettato — fermarsi e portarlo al coordinatore |
| Z0.3 | scalper: guardia `scalper-auto` (`scalper_service.py:295,363`) + `ferma_sessioni_al_nuovo_avvio` (`:225`) | `scalper_service_control` `stopped/paper`; nessuna sessione attiva | `select status, mode from scalper_service_control; select status, count(*) from scalper_control group by 1;` | sessione viva = scalper riparte da solo |
| Z0.4 | runner calcio dichiara il tetto e scende la scelta a `paper` all'avvio nuovo (`live_order_mode_avvio`, `runner.py:1641`, `modo_ordini.py:300-315`) | `order_mode='paper'` (mai salito), `order_mode_tetto` = `LIVE_ORDER_MODE` del `.env`, `order_mode_boot_id` nuovo | `select order_mode, order_mode_tetto, order_mode_tetto_at, order_mode_boot_id, order_mode_updated_by from betfair_live_settings;` | `order_mode='live'` dopo un avvio nuovo = regola «mai ereditare» violata |
| Z0.5 | processi e porte | ~16 processi dell'app (24/09: 15 + ora lo scalper-service), porte 47330-47338 in ascolto (47338 solo con `SCALPER_CANALE=1`) | `Get-NetTCPConnection -State Listen \| ? LocalPort -in 47330..47338` | porta mancante = processo non partito: log della console |

### Z1 — Feed unico (scanner) con età e fonte a video

| # | cosa fa ora | atteso | verifica | se non torna |
|---|---|---|---|---|
| Z1.1 | scanner Exchange Stream conflate 1000 ms, 1 livello (`safe_strategy/stream.py:18-22,64`), scrive `safe_strategy_scan`, pubblica su 47336 | chip `cr-feed`: età < 5 s; `cr-fonte-scan` = «canale locale»; `cr-fonte-stato-scanner` = «stato canale» | a video + `select max(updated_at), now()-max(updated_at) from safe_strategy_scan;` e `select updated_at from safe_strategy_status;` | fonte «database» con canale acceso = sottoscrizione rotta (AUDIT6 voce 14) |
| Z1.2 | sonda 47336 (sola lettura) | età riga p50 ~13 ms / p95 < 100 ms (misura del 24/09 h16:45); `saltati=0`; quote nulle in gioco 0 | `.venv\Scripts\python.exe -m Betfair.safe_strategy.tools.sonda_canale_scan_2026_09_18 --porta 47336 --minuti 15 --ogni 60` (processo: permesso dell'utente) | quote nulle > 0 = incidente del 17/09 |
| Z1.3 | confronto riga per riga DB↔UI (3 partite a caso, 1 in gioco) | prezzi back/lay, minuto e punteggio a video = `payload` della riga | `select event_id, updated_at, payload->'odds', payload->>'minute', payload->>'score' from safe_strategy_scan where event_id in (...);` | differenza con riga DB più recente = overlay del canale che perde (regola «vince solo il più recente») |
| Z1.4 | ritardo punteggi (IPS 2 s, promemoria «ritardo punteggi 2-3 s») | minuto/punteggio a video entro ~2-3 s dal cambio | osservazione su una partita in gioco | ritardo > 5 s costante = poll IPS fermo |

### Z2 — Runner calcio e tennis

| # | cosa fa ora | atteso | verifica | se non torna |
|---|---|---|---|---|
| Z2.1 | chip Runner (`ControlRoom.tsx:951`, fonte `cr-runner-fonte`): canale 47331 (hello, account ~20 s, ladder 200 ms, now 5 s) con ripiego `betfair_live_heartbeat` | «vivo», età ≤ 20 s, fonte «canale» | a video + `select * from betfair_live_heartbeat order by 1 desc limit 1;` (colonne da verificare) | età crescente con socket connesso = nessun `account` (AUDIT6 voce 6, punto 1) |
| Z2.2 | chip Runner tennis (`cr-runner-tennis`, `cr-runner-tennis-fonte`) dal canale 47332 | «vivo»; l'età può crescere a runner in attesa (reperto AUDIT6: nessun battito sul canale tennis) | a video | — (limite noto, non difetto) |

### Z3 — «Ordini reali»

| # | cosa fa ora | atteso | verifica | se non torna |
|---|---|---|---|---|
| Z3.1 | `RigaOrdiniReali` sovrappone `hello.mode` (tetto) e `now.state.order_mode` (effettivo) al DB (`RigaOrdiniReali.tsx:21-26`) | effettivo **PAPER**, tetto = `.env`, fonte ed età a video (`cr-ordini-reali-fonte`) | a video + SQL Z0.4 | effettivo ≠ min(tetto, scelta) = `modo_ordini` divergente dalla UI |

### Z4 — Per bot (accensione in paper, una alla volta)

Per ogni bot: (a) accensione dall'utente; (b) confronto riga di control ↔ chip/riga a video; (c) il bot legge i
dati giusti; (d) ordini paper ed esiti; (e) informazioni a video corrette; (f) uscite (automatiche e manuali).

**Omega** (`omega_control`, `omega_trades`, `omega_activity`, `omega_manual_requests`, canale 47334)

| # | cosa fa ora | atteso | verifica | se non torna |
|---|---|---|---|---|
| Z4.O1 | giro a `poll_interval_s` 20 s (5-60 s), sveglia dal canale solo con posizione viva | `cr-bot-fonte-omega` «stato canale N s» con N ≤ 60 | a video + `select stats->>'last_cycle' from omega_control;` (chiave da verificare in `_pubblica_stato`, `omega_service.py:7809`) | «stato db» fisso = push `omega_stato` non ricevuto |
| Z4.O2 | legge il feed dal canale fuso col DB (età max 5 s) | ogni ingresso ha `meta` con quote coerenti con `safe_strategy_scan` dell'istante | `select id, event_id, side, mode, price, size, status, placed_at, meta from omega_trades where placed_at::date = current_date order by id desc limit 20;` vs riga scan dell'istante | prezzo d'ingresso lontano dal feed = dato vecchio |
| Z4.O3 | ordini paper su coda DB (`_flumine_gate`, `omega_service.py:2708`) o ripiego REST FOK | righe `betfair_live_order_requests` `mode='paper'` e specchio `betfair_live_orders` `mode='paper'`; ripieghi REST visibili in `omega_activity` `live_fok_fallback` | `select id, action, mode, status, requested_at, processed_at, error from betfair_live_order_requests where requested_at > now()-interval '1 hour' order by id desc;` | una riga `live` = paper e live mischiati: **STOP** |
| Z4.O4 | uscite: `uscite_protezione` (default manuali) → proposte in `omega_manual_requests` `proposed` | proposta in scheda «Omega - uscita» con back al ms; approvazione → P29 fase 2 | `select id, status, payload->>'reason', created_at from omega_manual_requests order by id desc limit 10;` | proposta a video senza riga (o viceversa) = canale/DB incoerenti |
| Z4.O5 | stato mercato (fix `c5c8a92`: stato mancante → rilettura → rifiuto dichiarato) | nessun ingresso su mercato `SUSPENDED/CLOSED`; attività di rifiuto dichiarata | `omega_activity` ultimi 50 `kind` | ingresso su sospeso = difetto 17 |

**Mike** (`mike_control`, `mike_events`, `mike_trades`, `mike_activity`, `mike_requests`, canale 47333; esecuzione REST, fuori dallo specchio)

| # | cosa fa ora | atteso | verifica | se non torna |
|---|---|---|---|---|
| Z4.M1 | giro 1-5 s, `mike_stato` porta anche `control` (AUDIT6 voce 4) | `cr-bot-fonte-mike` «stato canale ≤ 5 s»; modalità e interruttori a video = `mike_control` | a video + `select status, mode, params->'uscite_automatiche', updated_at from mike_control;` | divergenza = `sovrapponiControl` sbagliato |
| Z4.M2 | frame live con hazard atlante v4 (`mike/dossier.py:306-321`) | `mike_events.live->>'hazard_versione'` = versione v4 sulle partite dove la lega è affidabile; altrove nota «atlante v3: recupero non modellato (motivo)» | `select event_id, live->>'hazard_versione', live->>'hazard_fase', live->>'hazard_nota' from mike_events where updated_at > now()-interval '1 hour';` (valore esatto della versione **da verificare**) | sempre v3 dopo il primo riempimento = `HAZARD_ATLAS_SYNC` spento o v4 non adottato |
| Z4.M3 | paper interno (FOK simulato, bet delay simulato `service.py`), righe `mike_trades` `mode='paper'` | nessuna riga in `betfair_live_orders` con ref `mike-t` in paper (Mike è fuori dallo specchio) | `select id, role, side, mode, price, size, status, placed_at from mike_trades where placed_at::date=current_date order by id desc limit 20;` | riga `live` = STOP |
| Z4.M4 | uscite: con `uscite_automatiche=false` la proposta va in `mike_events.ctx.uscita_proposta` | proposta in scheda (`SchedaMike` → `PropostaUscitaMike`); protezioni (cap perdita, copertura Over 4.5) automatiche anche spente | `select event_id, ctx->'uscita_proposta' from mike_events where ctx ? 'uscita_proposta';` | cap perdita non eseguito a uscite spente = gate sbagliato (`engine.py:2198`) |

**Safe** (`safe_strategy_control`, `safe_strategy_trades`, `safe_strategy_activity`, `safe_strategy_requests`, `safe_strategy_opportunities`, canale 47335)

| # | cosa fa ora | atteso | verifica | se non torna |
|---|---|---|---|---|
| Z4.S1 | giro 2 s (+ giro veloce 0,25 s su posizioni vive), `safe_stato` ogni giro | chip «stato canale ≤ 2 s»; `params_effective` a video (modi per strategia) = S-SAFE | a video + query comune di §3 Safe | — |
| Z4.S2 | BASE banca la perdente a 20-34 (Q1, `engine.py:207-208,1095`), veto campionati (Q4, `veto_campionati.py`, `engine.py:930`) | nessun ingresso base con lay fuori [20,34]; nessun ingresso su femminile/amichevoli/coppe/Bundesliga 2/Eerste Divisie…; motivo di scarto «veto campionato: … (corso)» nelle valutazioni | `select id, event_name, strategy, side, price, mode, meta from safe_strategy_trades where placed_at::date=current_date and strategy='base';` (lay in [20,34]) | ingresso fuori banda = Q1 non applicato; ingresso vietato = Q4 |
| Z4.S3 | tennis 1,02 (Q5) | `params.tennis.backMin` = 1,02 (migrazione §1.1) e nessun ingresso tennis sotto | SQL §1.1 + trade tennis di oggi | 1,01 = migrazione non applicata |
| Z4.S4 | hazard atlante v4 nelle note (`safe_strategy/opportunity.py:678-705`) | nota «atlante v4, <fase>[, recupero atteso ancora N']» o «atlante v3: recupero non modellato (motivo)» | dove finisce la nota: **da verificare** (attività o `meta` della proposta); `select ts, kind, payload from safe_strategy_activity where payload::text ilike '%atlante v%' order by ts desc limit 10;` | «hazard non verificato (atlante assente)» = atlante non caricato |
| Z4.S5 | ordini paper: FOK sempre, ref `safe-t<id>`, coda o REST; Safe tennis sempre REST (ref `safe_tennis-t<id>`, fix F1) | specchio `betfair_live_orders` `mode='paper'` per il calcio in coda; tennis senza specchio | `select client_order_ref, mode, status, size_matched, average_price_matched from betfair_live_orders where placed_at::date=current_date and client_order_ref like 'safe%';` (colonna del ref **da verificare**: `client_order_ref` è quella di flumine, il ref interno è `awlq<rid>`) | — |
| Z4.S6 | uscite: con strategia a uscite manuali la regola diventa proposta `proposed` | proposta in «Uscite», approvazione → P28 fase 2; protezioni (combo solidale, residui) automatiche | `select id, kind, status, payload->>'strategy', created_at from safe_strategy_requests order by id desc limit 20;` | — |
| Z4.S7 | modello/manuale: proposte del modello in «Opportunità», ordine a mano dalla scheda | la modalità della riga = `modalita_di_strategia('model'|'manual', …)` = paper | trade con `origin`/`strategy` model/manual di oggi | modalità diversa = barriera sbagliata |

**4 bot tennis** (`tennis_bot_service_control`, `tennis_bot_control`, `tennis_live_follow`, `tennis_live_orders`, `tennis_bot_activity`, canale 47337)

| # | cosa fa ora | atteso | verifica | se non torna |
|---|---|---|---|---|
| Z4.T1 | auto-mode: il ponte arma dal feed unico (`safe_strategy_scan` sport tennis, scanner vivo ≤ 30 s, tetto 5) (`tennis_bot_service.py:523-555,625,661`) | nota della riga «armato su N partite dal feed … tetto 5 · feed tennis: M partite, scanner X s fa»; `tennis_live_follow.origine='auto'` | `select event_id, status, origine from tennis_live_follow where status <> 'CLOSED';` e `select event_id, bot_key, status, mode, dry_run, uscite_automatiche from tennis_bot_control where status in ('requested','arming','armed','running','stopping');` | «acceso ma non apre: …» con feed pieno = auto-mode spento (migrazione) |
| Z4.T2 | righe per partita in paper: `mode='paper'`, `dry_run=false` (client simulato) (`_riga_armatura` `:714-738`) | tutte `mode='paper'`, `dry_run=false` | SQL sopra | `mode='live'` = STOP |
| Z4.T3 | ordini: flumine in-process (< 1 ms), specchio `tennis_live_orders` `source` = bot | righe `tennis_live_orders` `mode='paper'`, `source in ('tennis_scalper','tennis_pro','tennis_flb','tennis_swing')` | `select source, mode, status, count(*) from tennis_live_orders where coalesce(placed_at,updated_at)::date=current_date group by 1,2,3;` (stessa regola di `get_tennis_bot_orders_today`, `tennis_bot_service_control_2026-09-17.sql:175-195`) | — |
| Z4.T4 | uscite manuali: avviso arancione «posizione aperta da X min — chiudi con Chiudi» | a uscite manuali il target non parte, stop/protezioni sì; «Chiudi» → P31 fase 2 | a video + `tennis_bot_activity` | target eseguito a uscite manuali = gate tennis rotto |

**Scalper calcio** (`scalper_service_control`, `scalper_control`, `scalper_activity`, `betfair_live_orders` `source='scalper'`, canale 47338)

| # | cosa fa ora | atteso | verifica | se non torna |
|---|---|---|---|---|
| Z4.C1 | `giro_auto` arma dal feed calcio (tetto 2), righe `origine='auto'`, `dry_run=true` in paper | nota «auto-mode: N sessioni (M dal feed) - tetto 2 - feed calcio: …» | `select stats->'auto' from scalper_service_control;` `select event_id, status, dry_run, origine, stake from scalper_control where status in ('requested','arming','armed','running','stopping');` | `dry_run=false` in paper = STOP |
| Z4.C2 | specchio della sessione con `source='scalper'` (`scalper_session.py` `_SessionOrderMirror`) | ordini dello scalper nella voce «scalper», non «manuale app» | `select source, mode, count(*) from betfair_live_orders where placed_at::date=current_date group by 1,2;` | `source='runner'` per ordini dello scalper = specchio vecchio |
| Z4.C3 | canale 47338 (se `SCALPER_CANALE=1`) | riga scalper «dal canale locale, N s fa»; canale giù → «dal database» | a video | — |

### Z5 — Tempi degli ordini (F0)

- **Cosa fa ora:** `Betfair/stream/tempi_ordine.py` scrive una riga `tempi_ordine ...` per ordine (coda, canale
  47331, motore, tennis); interruttore `LIVE_TEMPI_ORDINE` acceso di serie (`F0_TEMPI_ORDINE_2026-09-25.md` §1-2).
  NON coperti: 4 bot tennis in-process, Mike e ripieghi REST, scalper calcio (§4 del referto).
- **Come si verifica:** salvare la console dell'app in un file (**da verificare dove finisce oggi**: referto F0 §7)
  e lanciare `python -m Betfair.stream.tools.leggi_tempi_ordine <file> --per-via`.
- **Atteso (soglie):** `interno_ms` p95 **< 10 ms** (obiettivo dell'audit strade §4.2); coda calcio (S1) dalla lettura
  al place entro le stime dell'audit (1,3-3,5 s decisione→placeOrders col worker a 1 s; l'app passa
  `LIVE_ORDER_QUEUE_POLL_SEC=0,15`, quindi atteso **meno**: AUDIT_TEMPO_REALE §1.5); canale 47331 (S2) 0,6-2,2 s
  (stima pessimista); tennis 47332 (S2t) 0,08-0,3 s; `ricezione_ms` della coda è MISTO (errore ~ -2 s se l'orologio
  del PC non è sincronizzato: servizio Ora di Windows). `decisione_ms` = `na` sulla coda e sui canali (manca
  l'istante della decisione: referto F0 §3).
- **Se non torna:** `interno_ms` p95 ≥ 10 ms = IO sul percorso dell'ordine; `presa_ms` alto = giro del worker lento
  (claim + IO delle righe prima).

### Z6 — Esiti degli ordini paper e messaggio d'abbinamento (B17)

- **Atteso:** ogni clic su una scheda termina con la striscia «ABBINATO TOTALMENTE/PARZIALMENTE a prezzo medio Y
  (Δ tick vs visto e vs segnale)», «NON abbinato (FOK)» o «rifiutato», con cartellino «paper · abbinamento simulato»
  (`SCHEDE_ABBINAMENTO_PREZZO.md` §1-3).
- **Verifica riga per riga:** medio e abbinato a video = `betfair_live_orders.average_price_matched`,
  `size_matched` (calcio in coda) / `tennis_live_orders` (tennis) / `mike_trades`/`safe_strategy_trades` (REST).
- **Se non torna:** «abbinato» con `size_matched=0` = difetto 2/3 del catalogo.

### Z7 — Transizioni di Omega

- **Cosa fa ora:** tabelle dei bot con `built_at` 11/09; migrazione O2 da applicare; pubblicazione MANUALE
  (`omega_transitions_publish('PUBBLICA')`) = decisione dell'utente (`O2_TRANSIZIONI_OMEGA_2026-09-25.md` §6).
- **Atteso (solo se l'utente ha pubblicato):** `select max(built_at) from omega_minute_transitions;` e
  `omega_ht_ft_transitions` = oggi; `select public.omega_transitions_status();` `published_at` valorizzato;
  `python -m Betfair.omega.tools.verifica_transizioni_2026_09_25` sezioni A/C/E senza differenze. Omega rilegge le
  tabelle ogni 6 h (`omega_service.py:104 EMPIRICAL_CACHE_TTL_S`), Mike solo al riavvio del processo
  (`mike/dossier.py:110-142`): il veto che «legge i conteggi di oggi» va provato DOPO un riavvio o dopo 6 h.
- **Se non torna:** `built_at` 11/09 = non pubblicato (atteso finché l'utente non decide).

### Z8 — TacticAI

- **Cosa fa ora:** fix `43e1468` (rho vincolato al dominio). I payload sono in
  `fixture_predictions.tactical_engine_json` (`tactical_engine/serving.py:263-264`), con `generated_at` e
  `markets.under_0_5` (`serving.py:159-183`).
- **Atteso:** nei payload generati dopo il fix nessun `under_0_5 < 0`:
  ```sql
  select count(*) filter (where (tactical_engine_json->'markets'->>'under_0_5')::numeric < 0) as negativi,
         count(*) as totale
    from public.fixture_predictions
   where (tactical_engine_json->>'generated_at')::timestamptz >= '<istante del primo run dopo 43e1468>';
  ```
  → `negativi = 0`. **Chi rigenera (verificato):** l'action `today_predictions_backfill`
  (`.github/workflows/today_predictions_backfill.yml:44,46`, esegue `python -m Prediction.today_predictions_backfill`),
  che in coda chiama il terzo motore additivo (`Prediction/today_predictions_backfill.py:2741-2746`:
  `from tactical_engine.serving import run_for_date as _tactical_run; _te_res = _tactical_run(target_date)`,
  avvolto in try/except non-fatale). Il controllo `negativi=0` va quindi fatto sui payload con `generated_at`
  successivo all'ultimo run di QUESTA action dopo `43e1468` (`gh run list --workflow
  today_predictions_backfill.yml -L 3`).
- **Se non torna:** negativi > 0 dopo il fix = il run non usa il codice nuovo o il fix non copre la previsione.

### Z9 — Catchup e quota API

- **Atteso:** `gh run list --workflow seasons_catchup.yml -L 3` verde; nel log il **REFERTO BUCHI**
  (**corretto**: `seasons_catchup.py:799` e seguenti — funzione `referto_buchi`, stampa `"REFERTO BUCHI"` a `:803`;
  non `:318-379` come nella versione precedente di questa riga) con il conto delle lega-stagioni aperte in calo rispetto a 961 (25/09 h19:20);
  contatore API sotto 7.500 con riserva 3.000 (`api_quota.py`).
- **Se non torna:** exit 1 con «BUCO VECCHIO» = buco > 3 giorni con budget (regola fail-loud).

### Z10 — Atlante v4

- **Atteso:** log `[atlante-domanda]` del processo dello scanner con leghe riempite (tetti 10/ciclo, 40/ora);
  righe `hazard_atlas_leghe` con blocco v4; note di Safe (Z4.S4) e frame di Mike (Z4.M2) con «v4».
- **Verifica:** colonne esatte di `hazard_atlas_leghe` **da verificare** (`migrations/hazard_atlas_2026-09-24.sql`).

### Z11 — Scalper auto-mode · Z12 — Tennis auto-mode

Coperti da Z4.C1-C3 e Z4.T1-T4. In più: con feed muto o scanner fermo NON si ferma niente (entrambi i referti §1);
partita uscita dal feed da ≥ 60 s → stop pulito delle sole sessioni `origine='auto'` (scalper); partita chiusa →
righe `stopping` (tennis).

### Z13 — Le regole da provare

| # | regola | come si prova | atteso | se non torna |
|---|---|---|---|---|
| Z13.1 | nessun bot opera all'avvio | Z0 | tutto `stopped/paper` | STOP del test |
| Z13.2 | paper e live mai insieme | (a) scalper: acceso paper → tentativo live → rifiuto SQL (P22); (b) Safe: con una strategia paper e il tetto paper nessuna riga `live` in nessuna tabella; (c) P&L a video mai sommati: `cr-bot-pnl-<id>` porta «in prova» | `select mode, count(*) from <ogni tabella trade/ordini> where …::date=current_date group by 1;` → solo `paper` | una riga `live` = STOP |
| Z13.3 | calcio e tennis distinti | P15 («solo tennis» dichiarato), topic separati (`safe_posizioni_calcio/tennis`, `canale_bot.py:89-93`), scheda calcio senza tennis e viceversa (`interruttoriDiSport`) | nessuna riga tennis nella scheda calcio | — |
| Z13.4 | kill-switch lascia passare solo le chiusure | con posizioni paper aperte: freno ON (P27, `RigaFreno.tsx`) → attendere un'apertura → OFF | coda calcio: aperture `error` «kill-switch ATTIVO: apertura RIFIUTATA», chiusure servite (`live_order_worker.py:3622-3633`); tennis: `TENNIS_KILL_SWITCH` rifiuta le aperture (`guardie_tennis.py:281-294`); **Corretto (R3 chiuso, commit `6ac2543`, non più aperto come nella versione precedente di questa riga): il freno ora è UNICO e ferma OGNI apertura, live E paper, di TUTTI i bot**, Mike e scalper calcio compresi: Safe calcio/tennis e Mike via `execution._freno_aperture` (+ Mike `_freno_resting_paper`), Omega via percorso paper col freno, scalper via `scalper_service.py:613-619 freno_supervisore()`/`scalper_session.motivo_freno()` (sessione non si arma, sorvegliante 2 s → force-flat e sessione `stopped`, supervisore non riavvia) | un'apertura passata col freno tirato, su QUALUNQUE bot = R3 rotto, **STOP** immediato (money-critical) |
| Z13.5 | uscite manuali = proposte, protezioni sempre automatiche | per ogni bot: uscite manuali → attendere una condizione d'uscita | proposta a video e sul DB, nessun ordine d'uscita discrezionale; stop/cap eseguiti | ordine d'uscita discrezionale a uscite manuali = gate rotto |

### Z14 — Confronto finale con il DB (il più approfondito)

Una sola sessione di query in SOLA LETTURA a fine giornata, confrontate con quello che la Control Room mostra
nello stesso istante (screenshot con ora):
1. conteggi per bot, modalità e stato delle righe di oggi (tutte le tabelle trade/ordini di Z4);
2. P&L paper di oggi per bot: somma DB (`pnl` delle righe regolate di oggi) vs `cr-bot-pnl-<id>`;
3. posizioni aperte: righe `open/pending` del DB vs `cr-posizioni`;
4. code: nessuna riga `pending/processing` più vecchia di 5 minuti;
5. `betfair_live_orders` e `tennis_live_orders`: ogni riga ha `mode='paper'`, nessun `bet_id` reale;
6. attività: nessun `kind` di errore critico non spiegato (`select kind, count(*) from <attività> where ts::date=current_date group by 1 order by 2 desc;`).

**Totale fase 2: 54 controlli** (Z0: 5, Z1: 4, Z2: 2, Z3: 1, Z4: Omega 5 + Mike 4 + Safe 7 + tennis 4 + scalper 3,
Z5: 1, Z6: 1, Z7: 1, Z8: 1, Z9: 1, Z10: 1, Z11/Z12: 2, Z13: 5, Z14: 6).

---

## 5. Ripristino

### 5.1 Fine fase 1 (le scrive l'utente nell'SQL editor, dopo averle viste)

Prima con i pulsanti (spegni, passa a prova, uscite come prima, importi come prima, Ordini reali `paper`,
kill-switch `false`, disarmo tennis). Poi SOLO le righe rimaste in stati intermedi (nessun servizio le chiude):

```sql
update public.omega_control         set status='stopped', stopped_at=now(), updated_at=now() where id=1 and status='stopping';
update public.mike_control          set status='stopped', stopped_at=now(), updated_at=now() where id=1 and status='stopping';
update public.safe_strategy_control set status='stopped', stopped_at=now(), updated_at=now() where id=1 and status='stopping';
update public.tennis_bot_service_control set status='stopped', mode='paper', stopped_at=now(), updated_at=now()
 where status in ('stopping','running');
update public.tennis_bot_control set status='stopped', stopped_at=now(), updated_at=now()
 where status in ('requested','arming','armed','running','stopping');   -- solo righe create dal test (filtrare per event_id)
-- righe di tennis_live_follow scritte APRENDO il Tennis Terminal durante la fase 1 (§1.5): cancellare
-- SOLO gli event_id assenti dalla fotografia iniziale (ON DELETE CASCADE ripulisce anche tennis_live_now/
-- tennis_live_ladder collegate, migrations/tennis_live.sql:56-65,73-82)
delete from public.tennis_live_follow where event_id in (<event_id aperti nel Terminal durante il test, non nella fotografia>);
```
Poi P32 (diff con la fotografia). Se `params` differisce, si rimette la colonna della fotografia **per intero**
(`update ... set params = '<json fotografato>'::jsonb`) — è l'unico caso in cui si riscrive `params`.

Rete di sicurezza (non sostituisce il ripristino): al primo avvio NUOVO dell'app Omega/Mike/Safe tornano
`stopped/paper` (`avvio_app.py:212-220`), il ponte tennis ferma gli interruttori **E la modalità**
(`tennis_bot_service.py:806-855 ferma_interruttori_al_nuovo_avvio`, riga 847-848: `status="stopped"`,
`mode="paper"` — fix R2, commit `6ac2543`, §9 aggiornato; NON più «senza toccare `mode`» come diceva la
versione precedente di questa riga), lo scalper ferma l'interruttore (guardia `scalper-auto`), `order_mode`
scende a `paper`.

### 5.2 Fine fase 2

1. L'utente: FERMA TUTTI → attesa che tutto sia `stopped` (i servizi vivi chiudono `stopping`).
2. Posizioni paper aperte: si lasciano sorvegliate o si chiudono col «Chiudi» (decisione dell'utente).
3. «Ordini reali» → `paper`; kill-switch → `false`; uscite di ogni bot → valore della fotografia.
4. Query di §1.5: tutto `stopped/paper`, code vuote.
5. L'app la chiude l'utente (mai noi).

---

## 6. Cosa NON si testa qui e perché

| cosa | perché |
|---|---|
| qualunque ordine LIVE (bot, ladder, tennis per partita senza dry-run) | ordine dell'utente: paper; il live viene solo dopo che il paper conferma (processo standard §5) |
| live per partita dei bot tennis | impossibile dal codice oggi: `tennis_bot_arm` scrive sempre `mode='paper'` (`tennis_bot_control_mode_2026-09-24.sql:18-23,99-106`); decisione T1 dell'utente |
| strada unica degli ordini via canale (porte di Safe/Omega, motore del runner) | interruttori assenti; decisione D-1 dell'utente (col canale i bot operano solo sulle partite seguite) |
| ramo coda di Mike (`MIKE_USE_FLUMINE_QUEUE`) | rotto per costruzione (M1), da non accendere prima di F7 |
| replay/banco | non è un e2e: si fanno a parte, uno per bot in sequenza (§0.5) |
| approvazione della singola chiusura dello scalper | non implementata (dubbio 4 del referto uscite) |
| trading manuale dal ladder in LIVE | fuori dal perimetro paper; il PAPER del ladder si può provare in Z6 se l'utente vuole |
| B17 «a mercato vs prezzo visto» per le uscite Omega/Safe | decisione aperta dell'utente: oggi il servizio esegue a mercato, il prezzo visto si salva soltanto |
| ~~kill-switch in Control Room | non esiste (solo Segui Live): da decidere, non da testare~~ | **corretto (6ac2543): ORA esiste** (`RigaFreno.tsx`, P27): SI TESTA, non va più tolto dal perimetro |
| stop giornaliero del tennis (E34) | decisione dell'utente del 25/09 h17:15: resta com'è |
| forza pre-partita nell'atlante v4 | non collegata (servono id squadra): decisione dell'utente |
| scanner/Betfair sotto carico, riconnessioni, 10 connessioni per app key | non provocabili senza toccare il sistema in esercizio |

---

## 7. Spazio per la sessione admin-26 (riempita)

Compilata dalla sessione admin-26 (Sonnet, delegato del coordinatore), SOLA DOCUMENTAZIONE: nessun
codice, nessun test eseguito, nessun accesso al DB, nessun processo avviato. Fonti: i referti in
`AUDIT_2026-09-25/` citati sotto, letti per intero dove serviva (§0-§7 di ognuno), più
`AUDIT_2026-09-24/AUDIT_TEMPO_REALE_2026-09-24.md` §0-§1 e `CRONOSTORIA.md` 25/09 h14:30. Formato di
ogni controllo: **# | controllo | azione/sonda (sola lettura) | riga/log attesa | criterio di
superamento | ripristino | se non torna**. Non ripete i controlli già in Z0-Z14 (§4): dove un pezzo è
già coperto lì, qui si aggiunge solo ciò che manca. `[DECISIONE UTENTE]` marca ciò che dipende da una
scelta ancora aperta.

### 7.1 Feed unico

Fonte: `AUDIT_2026-09-24/AUDIT_TEMPO_REALE_2026-09-24.md` §0-§1; `CRONOSTORIA.md` 25/09 h14:30: «REGOLA
per TUTTI i bot presenti e futuri: UN solo canale dati alimenta tutti i bot» (memoria
`feedback_un_canale_dati_tutti_i_bot_auto_mode_2026-09-25.md`). Z1 (§4) verifica già età/fonte dello
scanner per Omega/Mike/Safe e la Control Room; qui si verifica che i DUE bot costruiti oggi (scalper
auto-mode, tennis auto-mode) e l'auto-follow del runner calcio leggano la STESSA riga, non una fonte
loro.

| # | controllo | azione/sonda | riga/log attesa | superamento | se non torna |
|---|---|---|---|---|---|
| 7.1.1 | lo scalper legge il feed calcio dalla stessa tabella di Safe, non un poll proprio (`Db.feed_calcio`, `SCALPER_AUTO_MODE.md` §1: `safe_strategy_scan` con `sport='calcio'`, chiavi via `payload->k`) | confronto diretto: `select event_id, updated_at, payload->'odds' from safe_strategy_scan where sport='calcio' and event_id = <un evento armato dallo scalper> order by updated_at desc limit 1;` contro la nota `stats.auto` della riga `scalper_service_control` (`select stats->'auto' from scalper_service_control;`) nello stesso istante | l'`event_id` e l'età dichiarata nella nota scalper coincidono con `updated_at` della riga scan | fonte unica confermata | età/partite diverse fra le due letture = lo scalper ha una seconda fonte non dichiarata |
| 7.1.2 | il ponte tennis legge il feed dalla stessa tabella (`tennis_db.list_tennis_feed_rows`, `TENNIS_AUTO_MODE.md` §1: `safe_strategy_scan` `sport='tennis'`, SOLO `p1,p2,competition,open_date,inplay,mo_market_id,mo_status`, niente `score_raw`) | `select event_id, updated_at from safe_strategy_scan where sport='tennis' and event_id = <evento armato auto> limit 1;` contro `stats.auto` della riga `tennis_bot_service_control` interessata | stesso `event_id`, età coerente con «feed tennis: N partite, scanner X s fa» a video | fonte unica confermata | — |
| 7.1.3 | entrambi contano SOLO con lo scanner vivo (battito `safe_strategy_status` ≤ 30 s, `_SCANNER_VIVO_S`/`SCANNER_ALIVE_MAX_AGE_SEC`), non con un timeout proprio | fermare (in test, non in produzione) di osservare un battito > 30 s: nota scalper/tennis deve dire «feed … non disponibile (scanner fermo o lettura KO)», NON armare nuove partite | nessuna nuova riga `origine='auto'` mentre lo scanner è vecchio | coerente | armamento con scanner vecchio = soglia diversa da 30 s in uno dei due moduli |
| 7.1.4 | l'auto-follow del runner calcio (proattivo, non l'aggancio al volo) legge lo stesso feed, non uno stream Betfair diretto per scegliere le candidate (`AUTO_FOLLOW_TUTTI_I_BOT.md` §7: «Fonte del feed: `safe_strategy_scan` letta dal DB ogni 30 s») | log `[auto-follow] seguiti da soli X eventi (Y mercati) … feed F partite (db)` — la` F` deve avvicinarsi al conteggio di `select count(*) from safe_strategy_scan where sport='calcio' and updated_at > now()-interval '30 seconds';` | numeri coerenti (±1-2 per il ritardo dei 30 s) | coerente | `F` molto diverso = l'auto-follow legge un'altra vista |

**Ripristino:** nessuno, sola lettura. **Superamento della sottosezione:** tutti i consumatori nuovi
(scalper, tennis, auto-follow) leggono `safe_strategy_scan`; nessuno introduce un secondo canale.

### 7.2 Auto-follow degli eventi dei bot e strada unica degli ordini (decisione D-1)

Fonte: `AUTO_FOLLOW_TUTTI_I_BOT.md` (intero) e `STRADA_UNICA_BANCO_E_PAPER.md` §5 (intero). **Correzione
(verificata sul codice di oggi, il file è cambiato dopo la stesura di questa sezione):** l'auto-follow NON
è indipendente dal motore. In `Betfair/stream/runner.py:1896` la costruzione dell'auto-follow
(`_costruisci_auto_follow`, riga 1903) sta DENTRO lo stesso `if ch is not None and modo_avvio in ("PAPER",
"LIVE") and _motore_abilitato():` che costruisce il motore — `_motore_abilitato()` (`:1680-1681`) è
`MOTORE_ORDINI_CANALE=1`. **Senza quella variabile il blocco intero non gira: l'auto-follow non nasce
proprio** (nessun thread, `_MOTORE["auto"]` resta `None`), non solo l'invio ordini via canale. Quello che
RESTA indipendente e testabile separatamente è solo la STRADA degli ordini per singolo bot
(`SAFE_ORDINI_VIA_CANALE`, `OMEGA_ORDINI_VIA_CANALE`): con motore acceso e questi spenti, gli ordini dei
bot seguiti dall'auto-follow passano ancora sulla coda DB di sempre. **Prima di accendere, in quest'ordine** (`STRADA_UNICA_BANCO_E_PAPER.md`
§5): (1) applicare `migrations/live_follow_origine_2026-09-25.sql` (altrimenti l'auto-follow lavora solo
in RAM: nessuna riga, nessun badge, log «live_follow.origine NON disponibile»); (2) integrare il lavoro
auto-follow su master; (3) seguire in «Segui live» solo le partite che si vogliono vedere nel Terminale
completo (gli eventi automatici sono «silenziosi»: niente `live_now`/ladder/segnali per loro).

| # | controllo | azione/sonda | riga/log attesa | superamento | se non torna |
|---|---|---|---|---|---|
| 7.2.1 | auto-follow attivo SOLO se `MOTORE_ORDINI_CANALE=1` (nasce dentro lo stesso `if` del motore, `runner.py:1896-1903`; `RUNNER_AUTO_FOLLOW=0` lo spegne separatamente col motore comunque acceso) | grep log avvio runner: `[runner] AUTO-FOLLOW ATTIVO: i bot operano da soli su tutte le partite (aggancio al volo + feed), tetto 180 mercati …` | riga presente all'avvio, SOLO con `MOTORE_ORDINI_CANALE=1` | comparso | assente con `MOTORE_ORDINI_CANALE=1` e `RUNNER_AUTO_FOLLOW≠0` = auto-follow non montato (verificare integrazione su master); assente con `MOTORE_ORDINI_CANALE` spento = atteso, non un difetto |
| 7.2.2 | motore ordini sul canale acceso (`MOTORE_ORDINI_CANALE=1`) | grep `[runner] motore ordini ATTIVO sul canale 47331 (diario …\_diario_ordini)` | riga presente | comparso | assente = interruttore non letto (riavvio mancato) |
| 7.2.3 | Safe calcio passa sul canale di comando (`SAFE_ORDINI_VIA_CANALE=1`, DOPO aver visto il motore attivo) | grep `[safe.bot] ordini calcio via canale di comando ws://127.0.0.1:47331/comando/safe`; poi un'apertura Safe base in paper | attività `canale_inviato` `{trade_id, mode:"paper", ref:"safe-t<id>", seq, price, size, chiusura}`: `select ts, kind, payload from safe_strategy_activity where kind='canale_inviato' order by ts desc limit 5;` | riga presente entro pochi secondi dall'ordine | assente = Safe non è passato dal canale (ripiego coda DB silenzioso: verificare log d'errore) |
| 7.2.4 | sulla riga del trade compaiono le marcature del canale | dopo 7.2.3, sulla stessa riga | `select id, meta->>'canale_ref', meta->>'canale_ack_seq', meta->>'canale_ack_ms', meta->>'canale_fase' from safe_strategy_trades where id = <trade_id>;` → tutte e 4 valorizzate | valorizzate | NULL = la scrittura delle marcature non è arrivata |
| 7.2.5 | età del comando sotto soglia | diario `DATA_DIR/_diario_ordini/<AAAA-MM-GG>.jsonl`, riga `{"tipo":"inviato","canale":"comando",...}`: età = `ts_ms − parametri.creato_ms` | < 3000 ms (`max_eta_ms`) | < 3000 | ≥ 3000 = comando scaduto lato motore, l'ordine non parte da lì |
| 7.2.6 | Omega passa sul canale (`OMEGA_ORDINI_VIA_CANALE=1`, DOPO Safe ok) | grep `[omega] ordini via canale di comando …/comando/omega`; poi un'apertura Omega in paper | stesse attività/marcature di Safe su `omega_activity`/`omega_trades` | comparse | — |
| 7.2.7 | nessuna riga nuova sulla coda DB per gli ordini passati dal canale | dopo 7.2.3-7.2.6 | `select count(*) from betfair_live_order_requests where requested_at > now()-interval '5 minutes';` → 0 per i trade appena aperti via canale | 0 righe nuove | riga presente = l'ordine è passato ANCHE dalla coda (doppio invio, money-critical: **STOP**) |
| 7.2.8 | aggancio al volo: comando su una partita non ancora seguita dal runner | ordine di un bot su una partita fuori da «Segui live» e fuori dal feed appena entrata | diario: `in_aggancio` (market_id, scadenza_ms) poi `agganciato` (`attesa_ms`); log `[motore] <ref> in attesa dell'aggancio di 1.xxx (scade fra 3000 ms)` poi `[motore] <ref> agganciato dopo NNN ms: eseguo` | agganciato entro 3000 ms, un solo ordine eseguito | mai `agganciato`, solo `rifiutato` = SUB_IMAGE non arrivato entro 3000 ms dal vivo (§8 del referto, non provato in rete) |
| 7.2.9 | mai più «non sottoscritto» sui comandi dei bot | grep sul log del runner per l'intera fase 2 | 0 occorrenze di `market … non sottoscritto nel runner` | 0 | presente = l'auto-follow non ha agganciato in tempo, il vecchio rifiuto è tornato |
| 7.2.10 | tetto mercati 180 rispettato, follow manuali mai espulsi | seguire 2-3 partite a mano PRIMA di accendere i bot (rischio noto, §2 del referto: `LIVE_MARKET_TYPES` **[DECISIONE UTENTE]**, non impostata: ogni partita a mano sottoscrive 50-100 mercati) | log `[auto-follow] seguiti da soli X eventi (Y mercati) + manuali Z mercati = T/180 …`; T ≤ 180 sempre | T ≤ 180, follow manuali mai fra gli espulsi | T supera 180 o un manuale sparisce = tetto/priorità rotti; con 2-3 manuali pieni, ogni comando bot riceve `tetto_mercati_pieno` (atteso finché `LIVE_MARKET_TYPES` non è deciso) |
| 7.2.11 | righe `live_follow` automatiche coerenti | durante la fase 2 | `select event_id, status, origine from public.live_follow where origine='auto';` → `STREAMING` mentre seguite, mai riscritte se manuali; all'avvio nuovo le auto rimaste aperte vanno `CLOSED` | coerente col log | una riga manuale con `origine` cambiato = bug d'insert (mai atteso, l'update è filtrato `WHERE origine='auto'`) |
| 7.2.12 | righe in volo al riavvio dell'app (paper) | riavviare l'app con un comando in `in_aggancio`/parcheggiato | dopo TTL+60 s la riga passa `error` con `canale_senza_esito` | nessun fill inventato | riga rimasta `pending` oltre TTL+60 s senza `error` = watchdog non scattato |
| 7.2.13 | Mike e Safe tennis restano fuori dalla strada canale (F7/F8, per costruzione) | verificare che nessun interruttore `MIKE_USE_FLUMINE_QUEUE` / `SAFE_TENNIS_ORDINI_VIA_CANALE` sia stato acceso | `.env`: entrambi assenti; Mike continua REST, Safe tennis continua REST (`AUDIT_STRADE_ORDINE` par. 1.4) | assenti | presente = accensione non autorizzata di un percorso rotto (M1) o non montato (F8): **non accendere** |

**Ripristino (in questo ordine, «10 secondi» per la strada canale, §5 STRADA_UNICA):** (1) spegnere
`SAFE_ORDINI_VIA_CANALE`/`OMEGA_ORDINI_VIA_CANALE`; (2) riavvio dell'app; (3) `MOTORE_ORDINI_CANALE`
spento per ultimo — SPEGNENDO il motore si spegne ANCHE l'auto-follow (stesso `if`, `runner.py:1896-1903`):
non è un interruttore a parte, non resta acceso a motore spento. `RUNNER_AUTO_FOLLOW=0` resta utile SOLO
per tornare al comportamento di prima TENENDO il motore acceso (motore attivo, auto-follow spento: un bot
che tenta un ordine su una partita non seguita riceve `mercato … non sottoscritto nel runner`, il rifiuto
di sempre — non `motore_non_attivo`, che è la risposta a motore spento del tutto, guardia
`_GUARDIA_AVVIO`/`_motore_attivo() is None`).
**Superamento della sottosezione:** tutti i controlli 7.2.1-7.2.13 passano, nessuna riga live in nessuna
tabella (Z13.2 già lo verifica trasversalmente), nessuna riga duplicata sulla coda DB.

### 7.3 Atlante v4

Fonte: `ATLANTE_V4_COLLEGATO.md` (intero). Il generatore e il motore a domanda accumulano lo stato v4
per lega dalle stesse righe del v3 (una colonna in più: `raw_json->fixture->status->extra`); Safe e Mike
consultano `consulta_atlante_v4` col tempo ricavato dal feed. Z4.S4/Z4.M2 (§4) già chiedono la nota/il
frame «v4»; qui si aggiungono i controlli sulla generazione, sul ripiego dichiarato e sui costi.

| # | controllo | azione/sonda | riga/log attesa | superamento | se non torna |
|---|---|---|---|---|---|
| 7.3.1 | `HAZARD_ATLAS_SYNC=1` acceso (messo dal coordinatore il 25/09 h13:05, §1.2 riga 85) | grep nel `.env` | presente = 1 | presente | assente = i bot NON scaricano il file live, tutto resta sul v3 (comportamento noto, non un guasto) |
| 7.3.2 | primo riempimento del motore a domanda con v4 | grep sul log dello scanner (thread Safe, dove vive `atlante_a_domanda`) | righe `[atlante-domanda] …` con leghe che passano da v3 a v4 | comparse entro il tetto (10 leghe/ciclo, 40/ora, pausa 5 s) | nessuna riga = il motore non sta ricalcolando (blocco v4 assente per costruzione, ripiego v3 sempre) |
| 7.3.3 | stato v4 scritto per lega | `select league_id, league_name, n_fixtures, updated_at, stato ? 'v4' as ha_v4, jsonb_path_query_first(stato, '$.v4.affidabile') as affidabile_v4 from public.hazard_atlas_leghe order by updated_at desc limit 20;` (colonne vere: `league_id, league_name, n_fixtures, last_fixture_date, updated_at, stato jsonb, fixtures jsonb`, `migrations/hazard_atlas_2026-09-24.sql:28-36` — risolve il punto 8 di §8 del piano) | righe con `ha_v4=true` per le leghe osservate oggi | `ha_v4=true` compare | tutte `false` dopo ore di gioco = `aggiungi_v4` non chiamato (M3/M4 della falsificazione, referto §5) |
| 7.3.4 | Safe: nota con versione | Z4.S4 chiede dove finisce la nota; qui il testo esatto | nota su una proposta/trade contiene `atlante v4, <fase>[, recupero atteso ancora N']` oppure `atlante v3: recupero non modellato (<motivo>)` (mai un terzo formato); esempio reale in `ATLANTE_V4_COLLEGATO.md` §3 | uno dei due formati sempre presente | nota senza «atlante v3»/«atlante v4» = versione non dichiarata (difetto di falsificazione M20) |
| 7.3.5 | Mike: chiavi nuove nel frame live | `select event_id, live->>'hazard_versione', live->>'hazard_fase', live->>'hazard_recupero_atteso_min', live->>'hazard_atlas' from mike_events where updated_at > now()-interval '1 hour';` (chiavi vere: `hazard_versione`, `hazard_fase`, `hazard_recupero_atteso_min` — `dossier.py:309-321`; risolve parzialmente il punto 7 di §8 del piano, lato Mike) | `hazard_versione` = `v4` sulle leghe affidabili, altrove `v3` con la nota di ripiego | coerente | `hazard_versione` sempre NULL = i campi non arrivano nel frame (dossier non aggiornato) |
| 7.3.6 | `hazard_recupero_atteso_min` è volatile (cambia a ogni minuto del recupero), `hazard_versione`/`hazard_fase` no | due letture della stessa partita a 60 s di distanza in recupero | `hazard_recupero_atteso_min` diverso, `hazard_versione`/`hazard_fase` uguali | coerente | `hazard_versione` cambia da un giro all'altro sulla stessa fase = instabilità del calcolo |
| 7.3.7 | Omega non consuma hazard (invariato) | `select payload from omega_activity where kind ilike '%hazard%' order by ts desc limit 5;` | nessuna riga (Omega usa solo `h2h_hint`, invariato e provato dal test `test_omega_h2h_invariato_col_v4`) | 0 righe | righe presenti = Omega ha iniziato a leggere hazard: cambio di strategia non autorizzato, **portare all'utente** |
| 7.3.8 | ripiego v3 dichiarato (lega non affidabile o blocco assente) | osservare una lega appena entrata nel v4 (< 300 partite affidabili) | nota/frame con «atlante v3: recupero non modellato (…)», stesso minuto/valore di ieri | dichiarato | ripiego silenzioso (nota generica senza motivo) = M11 della falsificazione tornata viva |

**Ripristino:** nessuno, sola lettura; per tornare al solo v3 basta spegnere `HAZARD_ATLAS_SYNC` e
riavviare (i bot non trovano il file live, ripiegano tutti su v3). **Non verificato dal referto (§7,
punto 1-2), da guardare dal vivo:** se `hazard_atlas_leghe` ha già righe prima di stasera e se il motore
gira almeno un ciclo reale sul DB.

### 7.4 Catchup e referto buchi

Fonte: `BACKFILL_AUTOMATICO_STAGIONI.md` (intero). Non è un test dei bot di trading: è la catena GitHub
Actions (Daily → mapper → catchup) che tiene `matches`/dettagli aggiornati; Z9 (§4) già chiede il verde
del workflow e il contatore quota sotto soglia. Qui si aggiungono i controlli sul CONTENUTO del referto
e sullo stato delle tabelle nuove, utili anche fuori dalla finestra della fase 2 (girano di notte).

| # | controllo | azione/sonda | riga/log attesa | superamento | se non torna |
|---|---|---|---|---|---|
| 7.4.1 | migrazione applicata PRIMA di qualunque catchup | `select routine_name from information_schema.routines where routine_name in ('record_fixture_detail_checks','season_detail_gaps','season_gaps_summary') and routine_schema='public';` → 3 righe | 3 funzioni presenti | 3/3 | mancanti = catchup e orchestratore si fermano con «applica migrations/season_gaps_2026-09-25.sql» (exit 2): atteso finché non applicata |
| 7.4.2 | indice utile sulle tabelle di dettaglio (senza, `match_odds` ~82M righe letta per intero) | `select * from public.season_detail_gaps(135, 2026, null) limit 5;` (RPC nuova, `season_gaps_2026-09-25.sql`) | risponde senza timeout (57014) | risponde | timeout o errore = manca l'indice (applicare anche `detail_fixture_idx_2026-09-25_SOLO_SE_MANCANO.sql`, che il blocco `DO` della prima migrazione avvisa) |
| 7.4.3 | REFERTO BUCHI nel formato atteso a fine run | `gh run view <ultimo run seasons_catchup.yml> --log \| grep "REFERTO BUCHI" -A 20` | tabella con colonne Lega/Stag/P/FT/da chiamare ev-fo-sg-ss-qu/att./costo~/aperto da; riga finale «DB SENZA BUCHI» oppure «BUCHI APERTI: N lega-stagioni, ~K chiamate, il più vecchio da G giorni» (formato esatto in `BACKFILL_AUTOMATICO_STAGIONI.md` §1.4, esempio reale incluso) | formato presente | assente/troncato = log incompleto o job fallito prima del referto |
| 7.4.4 | `BUCO VECCHIO` = fail-loud oltre 3 giorni con budget | cercare nel log `BUCO VECCHIO:` | se presente, exit ≠ 0 e causa dichiarata (errore API ripetuto / API vuota in attesa del 2° tentativo / 10 partite di fila in errore / non tentate nonostante il budget) | causa sempre dichiarata | `BUCO VECCHIO` senza causa = referto incompleto |
| 7.4.5 | contatore quota e riserva | log `[CATCHUP] quota all'avvio: contatore API N/7500 (fonte /status), riserva action 3000, margine M` | `N ≤ 7500`, `M = 7500 - N - 3000` coerente con la riga | coerente | margine negativo con lavoro proseguito = regola di quota bypassata |
| 7.4.6 | stato per lega-stagione (`stats_json` v2) | `select league_id, season_year, status, stats_json->>'buchi_aperti' as buchi_aperti, stats_json->>'buco_aperto_dal' as buco_aperto_dal, stats_json->>'ultimo_esito' as ultimo_esito from public.season_backfill_state order by updated_at desc limit 20;` (tabella/colonne: `season_backfill_state.stats_json`, `season_gaps.py:270-300`) | `status='completed'` SOLO se `season_end < oggi`, `current=False`, FT>0 e zero buchi aperti; altrimenti `in_progress` | coerente con la regola | `completed` con `buchi_aperti > 0` = regressione al comportamento vecchio (`league_orchestrator.py:387` pre-fix, sempre `completed`) |
| 7.4.7 | Retrain fra le action esclusive (R5) | `.github/workflows/seasons_catchup.yml` o log: `WORKFLOW_ESCLUSIVI_DEFAULT` | include `retrain_models.yml` oltre a Daily/Today/Results | presente | assente = concorrenza col retrain trattata come colpa (57014 tornerebbe) |
| 7.4.8 | dry-run dell'orchestratore su una lega nota (135) DOPO la migrazione | `python -m Betfair.stream.backfill.league_orchestrator --league 135 --season 2026 --dry-run` (processo: **permesso dell'utente**, nessuna chiamata API salvo `/status` gratuita) | tabella per stagione, zero chiamate, avviso se FT senza dati e flag False | exit 0, nessuna scrittura | exit 2 «applica migrations/season_gaps…» = la 7.4.1 non è passata |

**Ripristino:** nessuno per 7.4.1-7.4.7 (sola lettura); 7.4.8 è un dry-run dichiarato senza scritture, non
serve ripristino. **Non è un test dei bot**: non blocca né sblocca la fase 2, ma va riportato all'utente
se `BUCHI APERTI` cresce durante il giorno del test.

### 7.5 Schede B17 (prezzo visto vs segnale, abbinamento reale)

Fonte: `SCHEDE_ABBINAMENTO_PREZZO.md` (intero). Z6 (§4) chiede già la striscia a video («ABBINATO
TOTALMENTE/PARZIALMENTE…») e il confronto con `average_price_matched`/`size_matched`. Qui si aggiungono i
controlli sul `prezzo_segnale` salvato in coda (la parte nuova del 25/09, non ancora in Z6) e sul
`useSeguiOrdini` (dove la riga viene seguita dopo il clic).

| # | controllo | azione/sonda | riga/log attesa | superamento | se non torna |
|---|---|---|---|---|---|
| 7.5.1 | Safe opportunità: `prezzo_segnale` salvato sulla riga | clic su una proposta Safe (opportunità) | `select id, meta->>'prezzo_visto', meta->>'prezzo_segnale' from safe_strategy_trades where id = <trade_id>;` → `prezzo_segnale` = `price_at_decision` della proposta (o `price` se assente) | valorizzato | NULL = `bot_service.py:2778` non ha scritto la chiave |
| 7.5.2 | Safe uscita: idem sulla chiusura | clic su «chiudi» di una proposta Safe con `price_at_decision` noto | `select payload->>'prezzo_segnale' from safe_strategy_requests where id = <request_id>;` | valorizzato | NULL = non salvato nel contesto della richiesta |
| 7.5.3 | Omega uscita: `p_contesto` con `back_price` | clic su «chiudi» Omega (richiede `migrations/omega_request_approve_contesto_2026-09-25.sql`: `omega_request_approve(p_id, p_price DEFAULT NULL, p_contesto DEFAULT NULL)`) | `select id, payload->>'price_visto', payload->>'price_visto_at', payload->>'prezzo_visto_ctx' from omega_manual_requests where id = <request_id>;` → tutte e 3 valorizzate | valorizzate | tutte NULL con la migrazione applicata = RPC vecchia ancora viva (`pg_get_functiondef`); **senza** la migrazione, ripiego dichiarato su `p_id` (atteso, non un difetto) |
| 7.5.4 | Mike proposta d'uscita: `prezzo_segnale`/`clic_ms` nel contesto | clic su «approva uscita» Mike (`migrations/uscite_automatiche_mike_2026-09-25.sql`, kind `approva_uscita`, richiede `chiave` non vuota altrimenti eccezione) | `select id, status, payload->>'chiave', payload->'contesto'->>'prezzo_segnale', payload->'contesto'->>'clic_ms' from mike_requests where kind='approva_uscita' order by id desc limit 5;` | `prezzo_segnale` = `ordini[0].prezzo` al clic, `clic_ms` valorizzato | valorizzati | NULL = contesto non passato dalla scheda (`PropostaUscitaMike.tsx`) |
| 7.5.5 | testi esatti della striscia a video (`esitoAbbinamento.test.ts`, inchiodati) | osservare a video dopo un ordine paper | uno fra: `ABBINATO TOTALMENTE a prezzo medio X (Δ vs visto … vs segnale …), size Y`; `ABBINATO PARZIALMENTE: …`; `NON abbinato (FOK): il book non copriva l'intera size, ordine ucciso senza abbinamento`; `rifiutato: …`; cartellino «paper · abbinamento simulato» | testo combacia con uno degli esempi | combacia | testo diverso = `esitoAbbinamento.ts` cambiato senza aggiornare il test (regressione) |
| 7.5.6 | fonte ed età della striscia | a video, accanto al messaggio | una fra: «canale del bot al ms (seq N) · T s fa»; «database (ripiego: lettura del blocco del bot) · T s fa · esito Betfair dal canale ordini del runner (seq N, matched)»; «coda del bot (riletta ogni 2 s) · T s fa» | dichiarata | assente = `useSeguiOrdini` non ha trovato la riga entro 90 s dal clic |
| 7.5.7 | «Chiudi» di riga (tutti i bot): messaggio dopo la richiesta | clic su «Chiudi» di una riga qualunque | Omega/Safe: gamba `closes_trade_id` seguita fino al messaggio; Mike/tennis: righe NUOVE del bot sulla partita (per Mike, stesso ruolo); scalper: NIENTE messaggio (ferma una sessione, non è un ordine — atteso, non un difetto) | coerente col bot | messaggio d'abbinamento sul «Chiudi» dello scalper = comportamento diverso da quanto dichiarato, verificare |
| 7.5.8 | punto NON eseguito, resta aperto (portarlo all'utente se emerge in fase 2) | — | B17 «esecuzione a mercato vs prezzo visto»: Omega/Safe eseguono ancora a mercato, il prezzo visto si SALVA soltanto, non vincola l'esecuzione | atteso (nessun cambio di esecuzione) | un ordine che rifiuta per «fuori banda» quando B17 non esegue ancora a banda = comportamento non previsto oggi, **fermarsi e chiedere** |

**Ripristino:** nessuno, sola lettura (le richieste/trade restano quelle della fase 2, ripristinate con
§5.2). **Non fatto/non verificato dal referto (§6), da sapere prima di dare torto al test:** Mike prima
del clic non è al ms (proposta con `mercato`/`selezione` simbolici, non `market_id`/`selection_id`); le
gambe di Mike e tennis sono per CORRELAZIONE (stesso ruolo, stesso istante), non per chiave; il prezzo
visto del «Chiudi» non arriva al servizio (solo a video, per il Δ).

### 7.6 Scalper auto-mode

Fonte: `AUDIT_2026-09-25/SCALPER_AUTO_MODE.md` (intero). Z4.C1-C3 e Z11 (§4) già coprono l'armamento dal
feed, lo specchio `source='scalper'` e il canale 47338. Qui si aggiungono i controlli sull'interruttore
globale, sui tetti e sulla decisione aperta del live automatico.

| # | controllo | azione/sonda | riga/log attesa | superamento | se non torna |
|---|---|---|---|---|---|
| 7.6.1 | ordine di applicazione delle migrazioni (§1.1 del piano già lo elenca, qui la CONSEGUENZA se invertito) | `select proname from pg_proc where proname in ('scalper_auto_activate','scalper_auto_stop','scalper_auto_update','scalper_uscite_automatiche');` | 4 funzioni presenti | 4/4 | mancanti = `uscite_automatiche_scalper_2026-09-25.sql` non applicata prima di `scalper_auto_mode_2026-09-25.sql` (l'ordine è nel referto §4) |
| 7.6.2 | paper e live mai insieme sull'interruttore globale | tentare `scalper_auto_activate('live')` con lo scalper già `running/paper` (dalla UI, doppio consenso) | rifiuto della RPC, nessuna scrittura | rifiutato | scrittura avvenuta = guardia rotta, **STOP** |
| 7.6.3 | tetto sessioni auto (default 2, env `SCALPER_AUTO_MAX_PARTITE`, max 4) | `select stats->'auto'->>'tetto' from scalper_service_control;` durante l'accensione | = 2 (o il valore dell'env, comunque ≤ 4) | coerente | tetto > 4 = clamp non applicato (`auto_mode.py` r.68-69,128) |
| 7.6.4 | vita della sessione rispettata (600 s maker, 4200 s con intervallo, 7800 s sniper/theta): non si arma una partita oltre KO+vita | osservare una partita in gioco da più tempo della vita del maker | nessuna sessione maker nuova armata su quella partita; sniper/theta invece sì se entro la loro vita | coerente | sessione maker armata oltre KO+600 s = filtro `vita_sessione_s` non applicato |
| 7.6.5 | stop pulito delle sole sessioni `origine='auto'` quando la partita esce dal feed da ≥ 60 s | osservare una sessione auto su una partita appena finita | `select event_id, status, origine from scalper_control where origine='auto' and status in ('stopping');` entro ~60-75 s dall'uscita dal feed; le sessioni `origine='manuale'` sulla stessa partita NON toccate | coerente | sessione manuale fermata insieme all'auto = filtro `origine` non applicato (money-critical se in live) |
| 7.6.6 | riarmo dopo spegni/riaccendi (gesto dell'utente) | fermare l'interruttore globale e riaccenderlo | le righe `stopped` DA PRIMA dell'accensione corrente si riarmano; quelle `stopped` a mano DOPO l'accensione corrente NO | coerente | riarmo di una sessione chiusa a mano nello stesso giro = regola di non-riarmo rotta |
| 7.6.7 | avvio nuovo dell'app: interruttore torna `stopped/paper` (già in Z0.3, qui il dettaglio della guardia) | riavvio dell'app | guardia «scalper-auto» in `avvio_app.ferma_al_nuovo_avvio`: nessun armamento finché il controllo d'avvio non riesce | coerente | armamento prima del controllo d'avvio = guardia bucata |
| 7.6.8 | **Corretto (verificato sul codice, D3 25/09):** `auto_mode.py:299 DRY_RUN_ALLA_NASCITA = True` e `:302-307 dry_run_alla_nascita(modalita)` tornano SEMPRE `True`, qualunque sia la modalità dell'interruttore (`del modalita` in corpo: il valore non la guarda nemmeno) — una sessione armata DA SOLA dal feed nasce SEMPRE in dry-run, **anche con l'interruttore in soldi veri**; uguale al tennis (7.7.7), non diverso come diceva la versione precedente di questo controllo. I soldi veri su una sessione li mette l'utente per SESSIONE, dallo `ScalperPanel` (ferma+riarma senza «Solo ARMATO», doppio gesto). In questa fase 2 non si prova il live (§0 regola 3): si verifica SOLO che (a) l'interruttore resti `paper` e (b) ogni riga armata dal feed nasca con `dry_run=true` | `select mode from scalper_service_control;` = `paper` per tutta la fase 2; `select event_id, dry_run, origine from scalper_control where origine='auto';` → `dry_run=true` su tutte | `paper`; `dry_run=true` su tutte le righe `origine='auto'` | `mode='live'` = violazione della regola 3, **STOP** immediato; una riga `origine='auto'` con `dry_run=false` = D3 rotta (money-critical), **STOP** |

**Ripristino:** `scalper_auto_stop()` dalla UI (ferma l'interruttore E tutte le sessioni attive in un solo
gesto); verificare `select status, mode from scalper_service_control;` → `stopped, paper` a fine fase 2
(già incluso nella fotografia di §1.5 se la migrazione è applicata prima). **Non rieseguito dal referto
(§7):** nessuna RPC provata contro il DB vero; l'upsert `ignore_duplicates` su `live_follow` non osservato
dal vivo.

### 7.7 Tennis auto-mode

Fonte: `AUDIT_2026-09-25/TENNIS_AUTO_MODE.md` (intero). Z4.T1-T4 e Z12 (§4) già coprono l'armamento dal
feed e la riga `mode='paper'`/`dry_run=false`. Qui si aggiungono i controlli sul messaggio di blocco, sul
tetto per bot e sulla classificazione delle uscite (quali sono gatabili e quali no).

| # | controllo | azione/sonda | riga/log attesa | superamento | se non torna |
|---|---|---|---|---|---|
| 7.7.1 | senza la migrazione `tennis_uscite_manuali_2026-09-25.sql` l'auto-mode resta SPENTO e lo dice | verificare `motivo_blocco` se la migrazione non è ancora applicata | «auto-mode spento: migrazione tennis_uscite_manuali_2026-09-25.sql non applicata» | dichiarato | bot armato su partite mai seguite a mano SENZA la migrazione = comportamento non atteso |
| 7.7.2 | tetto per bot (default 5, env `TENNIS_AUTO_MAX_PARTITE`, clamp 40; 0 = auto-mode spento solo per quel bot) | `select bot_key, params->>'auto_max_partite' from tennis_bot_service_control;` e nota a video «… tetto N …» | coerente col default/env | coerente | tetto > 40 o bot con `auto_max_partite=0` armato dal feed = clamp o spegnimento non rispettati |
| 7.7.3 | messaggio di blocco corretto per ogni causa (non solo «nessun evento seguito») | osservare la nota quando il bot non è armato | uno fra: «guardia d'avvio: …», «feed tennis vuoto: nessuna partita in-play ora», «feed tennis non disponibile (scanner fermo o lettura KO): …», «auto-mode spento: migrazione … non applicata», «auto-mode spento (tetto 0)», «nessuna partita armabile fra le N del feed (chiuse dall'utente, concluse o in errore)» | testo coerente con la causa reale | testo generico «acceso ma non apre» senza causa = il reperto originale (§0 del referto) non è chiuso |
| 7.7.4 | classificazione delle uscite: SOLO le discrezionali sono gatabili, protezioni sempre attive | con un bot a uscite manuali, attendere sia una condizione discrezionale sia una di protezione | target/scaglione/green (discrezionali) NON eseguiti; stop/time-stop/uscita strutturale/escalation/entry-timeout (protezioni) eseguiti comunque | coerente con la tabella per bot (swing/pro/FLB/scalper, `TENNIS_AUTO_MODE.md` §3) | target eseguito a uscite manuali = gate rotto (già in Z13.5, qui con la tabella esatta per bot) |
| 7.7.5 | lo scalper tennis NON è gatabile (decisione presa, non un buco): la UI deve dirlo | leggere il testo dell'interruttore uscite dello scalper tennis | «uscite: sempre automatiche» (non c'è scelta) | dichiarato | interruttore manuali disponibile per lo scalper tennis = la strategia è stata alterata (vietato) |
| 7.7.6 | avviso «posizione aperta da X min» a uscite manuali | bot a uscite manuali con una posizione aperta | avviso arancione permanente nella scheda partita; dato `stats.posizione_aperta_dal` sulla riga per partita | presente e coerente col tempo reale | assente dopo qualche minuto = `_aggiorna_uscite`/aggregazione del ponte non funziona |
| 7.7.7 | `[DECISIONE UTENTE]` live + auto-mode: le righe nascono SEMPRE `dry_run=true` anche in live (doppio gesto, come oggi) | non provare in live in questa fase 2; solo verificare la nota | in LIVE la nota aggiunge «LIVE: le partite nascono in dry-run, nessun ordine reale finché non lo togli per partita» | dichiarato | riga LIVE nata con `dry_run=false` senza gesto dell'utente per partita = violazione money-critical |
| 7.7.8 | partita automatica uscita dal feed: righe a `stopping`, follow chiuso solo se nessun bot lo vuole più | osservare una partita finita seguita solo in automatico | `tennis_bot_control` di quel bot va a `stopping`; `tennis_live_follow.status` passa `CLOSED` solo quando tutte le righe di quella partita sono chiuse | coerente | follow chiuso con righe ancora attive = perdita di sorveglianza su una posizione viva |

**Ripristino:** i bot li ferma l'utente dalla UI; `tennis_bot_service_set_uscite` riporta le uscite al valore
della fotografia se cambiate durante il test. **Corretto:** il default NON è più «automatiche» — dal 25/09 sera
(commit `890992f`, `uscite_manuali_default_2026-09-25.sql`, §1.1) il default di TUTTI i bot, tennis compreso, è
MANUALE (`uscite_automatiche=false`). Verifica finale: nessuna riga `tennis_live_follow`
`origine='auto'` rimasta `STREAMING` dopo il FERMA TUTTI. **Non verificato dal referto (§7):** la sintassi
PostgREST `alias:payload->chiave` e il valore `CLOSED` di `tennis_live_now.status` non sono stati
osservati dal vivo, solo dedotti dal codice.

### 7.8 Safe: veti aggiuntivi dai video (Q1/Q4/Q5, decisioni D5)

Fonte: `SAFE_Q1_Q4_Q5.md` e `SAFE_DECISIONI_D5.md` (interi). Z4.S2/Z4.S3 (§4) già chiedono la banda
20-34 e `backMin=1,02`. Qui si aggiungono i veti e le note che Z4.S2 non copre: campionati vietati con
finali/femminile dal nome squadra, scontri diretti veri, sfavorito estremo tennis. **Nessuna migrazione
nuova per queste decisioni** (D5 è solo codice: `engine.py`, `veto_campionati.py`, `selezione.py`, `db.py`,
`service.py`; l'unica migrazione dell'area resta quella opzionale di Q1, già in §1.1 riga 61).

| # | controllo | azione/sonda | riga/log attesa | superamento | se non torna |
|---|---|---|---|---|---|
| 7.8.1 | veto campionati vietati (femminile, amichevoli, Bundesliga/2. Bundesliga, Ered/Eerste Divisie) — Bolivia TOLTA il 25/09 | osservare candidati su questi campionati durante la fase 2 (nessun ingresso atteso) | nessuna riga in `safe_strategy_trades` con `event_name`/competizione su uno di questi; se rilevabile, motivo di scarto «veto campionato: <nome> (corso)» | nessun ingresso | ingresso su uno di questi = veto non attivo (regressione Q4) |
| 7.8.2 | veto SOLO sulle finali (non più tutte le coppe) | osservare una partita di coppa NON finale durante la fase 2 | ingresso AMMESSO (nessun veto); se la partita è una finale (round «Final» da API-Football o nome evento con «Final»), motivo «veto finale: round «Final» (API-Football)» o «… (Betfair)» | coerente con la fonte | veto su una partita di coppa non finale = regressione al comportamento pre-D5 |
| 7.8.3 | femminile riconosciuto anche dai nomi squadra (non solo dalla competizione) | osservare una partita con nome squadra tipo «… Women» / «(w)» in coda | esclusa; motivo «veto campionato: calcio femminile (nome squadra) (corso)» | esclusa e motivata | inclusa = riconoscimento solo per competizione, regressione |
| 7.8.4 | ESATTO: scontri diretti veri dal DB (non più solo il selection_hint dello scanner) | osservare la nota di una proposta ESATTO con h2h disponibile | nota con la forma «h2h: N partite, M con ≥4 gol · difesa avversaria X gol subiti · forze att A-B · def C-D»; senza h2h nel DB: «h2h: nessuno scontro diretto nel DB (non blocca)»; fixture non abbinata: «scontri diretti: dato assente» | una delle tre forme presente | nota assente o formato diverso = fonte non collegata (regressione Q7/D5) |
| 7.8.5 | soglia h2h 0,58 (4+ gol a fine 90', minimo 3 scontri) | proposta ESATTO con ≥3 h2h e quota di 4+ gol > 0,58 | scartata (check `h2hManyGoalsRateMax`) | scartata | non scartata = soglia non applicata o letta male |
| 7.8.6 | tennis: sfavorito estremo < 1,20 pre-partita (quota CONGELATA, non quella corrente) | proposta tennis dove il favorito pre-KO ha quota back congelata < 1,20 e si punterebbe il leader sfavorito | esclusa; nota «favorito pre-match X → sfavorito estremo: escluso» | esclusa e motivata | inclusa, o motivo diverso = `favSuperMax`/`pre_ko` non collegati |
| 7.8.7 | banca 20-34 nei check (Z4.S2 lo verifica sugli ingressi; qui il check visibile nella checklist/nota) | osservare la nota o la checklist di una proposta BASE | «Quota banca sfavorita 20–34», ok = lay in [20,34] estremi inclusi; lay assente = n/d (non «disponibile» generico) | testo coerente | testo vecchio «Quota banca sfavorita disponibile» = check non aggiornato (regressione Q1) |
| 7.8.8 | `params.tennis.backMin` letto dal DB, non dal default codice (Q5, già in §1.1 riga 60, qui la CONSEGUENZA se la migrazione manca) | `select params->'tennis'->>'backMin' from safe_strategy_control;` | `1.02`; se `1.01` la migrazione `safe_tennis_backmin_102_2026-09-25.sql` non è applicata | `1.02` | `1.01` con la migrazione dichiarata applicata = migrazione non eseguita davvero |

**Ripristino:** nessuno, sola lettura (le decisioni sono codice, non stato). **Dubbi aperti dai referti,
da portare all'utente se emergono in fase 2 (non correggere durante il test, regola 4 di §0):** soglia h2h
0,58 (il video suggerirebbe forse 20-30%, `SAFE_Q1_Q4_Q5.md` §11.1); soglia 4,0/1,20 per lo sfavorito
estremo è una proposta del delegato, non un numero detto nel video (`SAFE_DECISIONI_D5.md` §7.5); finali
di play-off/playout contate come finali, finali per il 3° posto no (da confermare).

---

### Osservazioni di admin-26 su §1-§8

1. **`LIVE_MARKET_TYPES` assente dalla tabella §1.2** (righe 72-87): l'auto-follow (`AUTO_FOLLOW_TUTTI_I_BOT.md`
   §2) segnala che SENZA questa variabile 2-3 partite seguite a mano riempiono i 180 posti e ogni comando
   dei bot su un'altra partita riceve `tetto_mercati_pieno`. È una `[DECISIONE UTENTE]` non ancora
   registrata nel piano: andrebbe aggiunta a §1.2 come riga propria.
2. **§8 punto 7 del piano** («valore esatto di `hazard_versione` … da verificare»): risolto lato Mike da
   `ATLANTE_V4_COLLEGATO.md` §3 (`dossier.py:309-321`): le chiavi sono `hazard_versione`, `hazard_fase`,
   `hazard_recupero_atteso_min` su `mike_events.live`. Resta aperto solo il lato Safe (dove finisce la nota
   sulla riga/attività: non risolto neanche da questa sessione, vedi 7.3.4).
3. **§8 punto 8 del piano** («colonne di `hazard_atlas_leghe` … da verificare»): risolto —
   `league_id, league_name, n_fixtures, last_fixture_date, updated_at, stato jsonb, fixtures jsonb`
   (`migrations/hazard_atlas_2026-09-24.sql:28-36`); lo stato v4 vive dentro `stato->'v4'`.
4. **§1.1 riga 62** cita `get_direction_eta_2026-09-25.sql` e `market_delays_ht_2026-09-25.sql` come «da
   verificare in cronostoria»: nessuno degli 8 referti letti da questa sessione li tocca; restano aperti,
   non risolvibili con le fonti assegnate.
5. Nessuna incoerenza trovata fra `STRADA_UNICA_BANCO_E_PAPER.md` §5 e la tabella `.env` di §1.2 sull'ordine
   di accensione (motore → Safe → Omega): coincide.
6. **D5 (Safe) non richiede nessuna migrazione**: `SAFE_DECISIONI_D5.md` §9 elenca solo file `.py`/`.ts`
   modificati. Il piano non lo dice esplicitamente in §1.1 (la riga 52 parla solo di Q1); utile saperlo per
   non cercare una migrazione che non esiste.

---

### 7.9 Verifica semantica (admin-26)

Ordine dell'utente (testuale): «Dovete verificare e certificare ogni singola cosa, anche le più subdole:
i dati che ricevono i bot e le predizioni che fanno sono corretti? quello che vede il trader è corretto?
i segnali per entrare a mercato rispettano tutte le condizioni? usano tutti i dati e tutto lo stack? è
verificato con il database? test globale volto anche a trovare bug nascosti. NON DATE NULLA PER
SCONTATO.» 7.1-7.8 verificano che i MECCANISMI/canali funzionino (transporto, tetti, guardie); qui si
verifica il CONTENUTO, con un ricalcolo INDIPENDENTE fatto importando la funzione di produzione vera
(mai una copia scritta per il test) e confrontandola con quello che i bot hanno scritto/mostrato nello
stesso istante. Cinque tagli, non tutti applicabili a ogni componente (usati sotto secondo quanto
richiesto dal coordinatore): **A** dati ricevuti veri; **B** stack/flusso completo usato per davvero;
**C** condizioni di ingresso rispettate; **D** quello che il trader vede è corretto; **E** casi subdoli
(bug nascosti). Fonti: referti in `AUDIT_2026-09-25/` citati per componente, riletti per intero dove
serviva, più lettura diretta del codice di produzione citato riga per riga. Regola comune a ogni voce
(non ripetuta a ogni riga): **sola lettura salvo dove dichiarato** (fermare un processo, saturare un
tetto, accendere il kill-switch in test sono azioni esplicite, mai un default); **KO = evidenza + file
di produzione:riga, nessuna correzione durante il test** (si scrive e si porta all'utente, regola 4 di
§0); i ricalcoli usano SEMPRE il modulo importato dalla produzione, mai una riscrittura della logica.

#### 7.9.1 Feed unico: i dati sono il libro Betfair vero?

Fonte: `AUDIT_2026-09-24/AUDIT_TEMPO_REALE_2026-09-24.md` §0-1 (già letto per 7.1); qui si aggiunge il
confronto con la VERITÀ del mercato, non solo con la fonte dichiarata.

| # | controllo | input dal DB/log e funzione di produzione importata (sonda, sola lettura) | confronto | criterio | se non torna (KO) |
|---|---|---|---|---|---|
| 7.9.1.A | i dati che i bot ricevono (payload di `safe_strategy_scan`) sono il libro Betfair VERO nello stesso istante, non un valore stantio; l'età dichiarata è l'età vera | per 3 istanti della stessa partita in gioco: `select event_id, updated_at, payload->'odds', payload->'cs'->>'market_id' from safe_strategy_scan where sport in ('calcio','tennis') and event_id=<evento> order by updated_at desc;` incrociata con la registrazione REALE dello stesso mercato scritta dal runner calcio a conflate 0 (`Betfair/stream/config_stream.py:87`, `runner.py:1942`): `_live_raw/<event_id>/<event_id>.raw.jsonl` (mcm) e `.scores.jsonl`/`.score.jsonl` (sidecar punteggi, calcio/tennis, `Betfair/stream/tools/validate_recordings.py:130,533`); se il mercato non è nella registrazione del runner in quell'istante, `listMarketBook` REST diretta sullo stesso `market_id` (client REST già istanziato dal runner, nessun poll nuovo) | prezzo/size al miglior livello back/lay del payload dello scanner (conflate 1000 ms, best offers, `Betfair/safe_strategy/stream.py:18-22,64`) contro il book vero conflate 0 nello stesso secondo; `now() - updated_at` (età dichiarata a video/canale) contro l'età vera del tick registrato | prezzo/size al best level uguali entro un tick Betfair (arrotondamento incrementi); età dichiarata entro ±2 s dall'età vera (margine: latenza scanner→DB p95 36 ms + conflate 1 s, misura 23/09) | differenza di prezzo/size al best level oltre un tick, o età dichiarata falsa oltre 2 s = evidenza (le due letture affiancate) + `Betfair/safe_strategy/stream.py:18-22,64`, nessuna correzione durante il test |

**Ripristino:** nessuno, sola lettura. **Superamento:** il payload dello scanner coincide col book vero
per prezzo/size al best level e per età dichiarata, su tutti e 3 gli istanti campionati.

#### 7.9.2 Auto-follow calcio + strada unica: lo stack intero, dal comando all'ordine sul Market

Fonte: `AUTO_FOLLOW_TUTTI_I_BOT.md` e `STRADA_UNICA_BANCO_E_PAPER.md` §5 (già lette per 7.2); qui si
aggiunge la riconciliazione riga per riga della catena e i casi subdoli non coperti da 7.2.

| # | controllo | input dal DB/log e funzione di produzione importata (sonda, sola lettura) | confronto | criterio | se non torna (KO) |
|---|---|---|---|---|---|
| 7.9.2.B | la catena comando→aggancio→diario→ordine sul Market è la STESSA cosa dall'inizio alla fine: nessun ref/prezzo/size che cambia lungo il percorso | per un comando su una partita non ancora seguita, in sequenza dal diario `DATA_DIR/_diario_ordini/<AAAA-MM-GG>.jsonl`: (1) riga `inviato/comando` (`ref`, `parametri.prezzo`, `parametri.size`, `parametri.creato_ms`); (2) `in_aggancio` (`market_id`, `scadenza_ms`) poi `agganciato` (`attesa_ms`), stessa `ref`; (3) riga `ordine` col `customerOrderRef`; (4) `select id, meta->>'canale_ref', meta->>'canale_ack_seq', meta->>'canale_ack_ms' from safe_strategy_trades/omega_trades where id=<trade_id>;` | `ref` del comando (1) = `ref` dell'aggancio (2) = `customerOrderRef` dell'ordine (3) = `meta.canale_ref` (4); `prezzo`/`size` del comando (1) contro prezzo/size dell'ordine realmente inviato al Market (3) | uguaglianza esatta di `ref` sulle 4 letture; uguaglianza numerica esatta (arrotondamento Betfair) di prezzo/size fra comando e ordine | `ref` diverso lungo la catena, o prezzo/size sull'ordine diverso dal comando = evidenza (le 4 righe affiancate) + `Betfair/stream/motore_ordini.py:1048,1070,1087`, **money-critical, si scrive e si porta all'utente** |
| 7.9.2.C | nessun ordine parte quando lo stato VERO del mercato (non una cache stantia) è SUSPENDED/CLOSED/INACTIVE | per ogni ordine eseguito in fase 2: stato del `MarketBook`/`marketDefinition` nello stesso istante dalla registrazione `_live_raw` (campo `status`); ricalcolo importando `Betfair.stream.trading.stato_mercato.mercato_operabile` (guardia unica, `stato_mercato.py:11`) sullo stesso `status`/`complete` | esito ricalcolato (`True`/`False`, motivo) contro se l'ordine sia partito o no, e contro l'eventuale attività `attesa_riapertura` (`KIND_ATTESA`, `stato_mercato.py:57`) | `mercato_operabile(...)[0] is False` deve corrispondere SEMPRE a nessun ordine partito; su SUSPENDED, `attesa_riapertura` scritta una sola volta per sospensione | ordine partito mentre il ricalcolo dà `(False, "SUSPENDED"/"CLOSED"/"INACTIVE")` = evidenza (book registrato + ordine) + `Betfair/stream/trading/stato_mercato.py:11-27`, **STOP, money-critical** |
| 7.9.2.E1 | canale caduto a metà fase 2: il bot DICHIARA il ripiego, non apre in silenzio su una seconda via (es. REST FOK diretto) | fermare (in test, permesso esplicito) il motore/canale 47331; `select payload from safe_strategy_activity where kind in ('canale_rifiutato','errore') order by ts desc limit 20;`; grep log per un'apertura calcio dopo la caduta | ogni riga di trade calcio nata DOPO la caduta contro la presenza di `meta.canale_ref` o una dichiarazione esplicita di ripiego | apertura dopo la caduta o assente (bot fermo/`error`) o dichiarata a testo come ripiego, mai silenziosa | apertura senza `canale_ref` e senza dichiarazione = secondo canale non sorvegliato, evidenza + log, **portare all'utente** |
| 7.9.2.E2 | tetto 180 saturo (2-3 manuali senza `LIVE_MARKET_TYPES`): un comando su partita nuova riceve SEMPRE `tetto_mercati_pieno`, mai un ordine alla cieca | saturare il tetto a mano, poi un comando su una quarta partita; diario + evento `order` del bot; log `[auto-follow] ... T/180 ...` | esito `tetto_mercati_pieno` sul diario contro `T` osservato nello stesso istante | `T=180` e motivo `tetto_mercati_pieno` coincidono sempre; 0 ordini eseguiti fuori tetto | ordine eseguito con `T=180` già raggiunto = tetto bucato, evidenza + `Betfair/stream/auto_follow.py:123,170`, **STOP** |
| 7.9.2.E3 | comando vecchio (età ≥ `max_eta_ms`=3000) sempre scartato, mai eseguito in ritardo | comando ritardato nel diario: età ricalcolata = `ts_ms − parametri.creato_ms` dalle 2 chiavi vere | età ricalcolata contro l'esito scritto (`rifiutato`/eseguito) | età ≥ 3000 ms → SEMPRE `rifiutato` col motivo dell'età/scadenza, mai eseguito | ordine eseguito con età ricalcolata ≥ 3000 ms = guardia bucata, evidenza + `Betfair/stream/motore_ordini.py:119`, money-critical |
| 7.9.2.E4 | kill-switch acceso MENTRE un comando è in aggancio (parcheggiato): esito SEMPRE `rifiutato`, mai un'esecuzione che scavalca | accendere il kill-switch (test, permesso esplicito) durante una finestra di aggancio nota; diario + evento terminale; ricalcolo di `LOW._kill_switch()`/`LOW._db_kill_switch()` (`motore_ordini.py:901-906`) sullo stato dei settings al momento in cui il book arriva | stato kill-switch ricalcolato al `_controlla` rifatto (`:1089`) contro l'esito effettivo | kill-switch ON al ricalcolo → SEMPRE `rifiutato` (`M_KILL`), mai un ordine eseguito dopo | ordine eseguito con kill-switch ON ricalcolato = guardia dell'aggancio non rifatta, evidenza + `motore_ordini.py:901-906,1089`, **STOP, money-critical** |
| 7.9.2.E5 | riavvio con posizione VIVA su una partita seguita solo in automatico: nessuna posizione persa, nessun fill inventato, sorveglianza (`live_follow`) non interrotta a torto | prima del riavvio: `select event_id, status, origine from live_follow where origine='auto';` + righe con esposizione viva; dopo il riavvio (gesto utente): stesse letture + riconciliazione per `ref` (`chiudi_orfani`, `runner.py:1850`) | righe di trade con esposizione viva prima del riavvio (stesso `trade_id`/`ref`) contro il loro stato dopo; `live_follow.origine='auto'` senza più bot ospitati contro `CLOSED` | nessuna posizione viva persa senza una chiusura vera su Betfair riconciliata per `ref`; nessun fill inventato nella finestra di riavvio | posizione viva prima del riavvio assente/chiusa dopo SENZA un ordine di chiusura vero riconciliato = evidenza + `runner.py:1850` e seguenti, **STOP, money-critical, portare all'utente** |

**Ripristino:** nessuno per i controlli di sola lettura; per 7.9.2.E1/E2/E3/E4 (azioni esplicite in test)
si torna allo stato di prima riaccendendo canale/motore, sbloccando il tetto e spegnendo il
kill-switch, come da §7.2. **Superamento:** tutte e 8 le voci passano, nessun secondo canale silenzioso,
nessuna posizione persa.

#### 7.9.3 Atlante v4: ricalcolo indipendente

Fonte: `ATLANTE_V4_COLLEGATO.md`, `ATLANTE_V4_FORZA_ID_SQUADRA.md`, `VALIDAZIONE_HAZARD.md` (interi).

| # | controllo | input dal DB/log e funzione di produzione importata (sonda, sola lettura) | confronto | criterio | se non torna (KO) |
|---|---|---|---|---|---|
| 7.9.3.B | `consulta_atlante_v4` ricalcolato dagli STESSI input (lega, tempo, minuto, gol, id squadra) dà lo stesso risultato della nota Safe e del frame Mike; il tempo 1T/2T-recupero è derivato correttamente dall'IPS su 3 istanti (1T, intervallo, 2T recupero); `hazard_atlas_leghe` è popolata dal motore a domanda per le leghe osservate; il ripiego v3 è dichiarato dove il blocco v4 manca | per 2-3 partite su leghe diverse: (a) `select league_id, stato from public.hazard_atlas_leghe where league_id=<lid>;` (colonne: `league_id, league_name, n_fixtures, last_fixture_date, updated_at, stato jsonb, fixtures jsonb`, `migrations/hazard_atlas_2026-09-24.sql:28-36`); (b) minuto/tempo/gol/id squadra dallo stesso istante (`safe_strategy_scan`) e da `_live_raw/<id>/<id>.scores.jsonl` (`matchStatus`, `timeElapsed`, `elapsedRegularTime`, `elapsedAddedTime`, come `AUDIT_2026-09-25/sonde/sonda_minuto_ips_recupero.py`); (c) nota Safe: `select payload from safe_strategy_activity where kind ilike '%hazard%' order by ts desc limit 10;` (scritta da `OpportunityModel._hazard_check`, `Betfair/safe_strategy/opportunity.py:630`); (d) frame Mike: `select event_id, live->>'hazard_versione', live->>'hazard_fase', live->>'hazard_recupero_atteso_min' from mike_events where updated_at > now()-interval '1 hour';` (chiavi scritte a `dossier.py:340-342`); ricalcolo: importare `Betfair.stream.scalper.atlante_v4.consulta_atlante_v4` (`atlante_v4.py:657`) con `atlas`=(a), `minute`/`tempo`/`goals`/`league_id`/`home_id`/`away_id`=(b) | `p`, `versione`, `fase`, `recupero_atteso_min`, `forza.moltiplicatore` del ricalcolo contro (c)/(d) per la stessa partita/minuto; `fase` ricalcolata contro `matchStatus`/`elapsedAddedTime` reali nei 3 istanti; conteggio `hazard_atlas_leghe` con `ha_v4=true` PRIMA vs DOPO un ciclo del motore a domanda (`Betfair.stream.scalper.atlante_a_domanda.ciclo`, `:237,421`, `aggiungi_partita`/`aggiungi_v4` a `:363,376`) | uguaglianza esatta `versione`/`fase`; `p`/`recupero_atteso_min` uguali entro l'arrotondamento mostrato; `fase` coerente con l'IPS reale nei 3 istanti; il conteggio `ha_v4=true` non diminuisce e cresce per le leghe osservate dopo un ciclo; ripiego v3 sempre con motivo dichiarato uguale a quello del ricalcolo | `versione`/`fase` del ricalcolo diversa dalla nota/frame, `fase` che non segue l'IPS reale, `hazard_atlas_leghe` ferma a 0 righe `ha_v4=true` dopo ore su leghe osservate, o ripiego v3 silenzioso = evidenza (le 4 letture affiancate) + `atlante_v4.py:657`, `opportunity.py:630`, `dossier.py:340-342`, `atlante_a_domanda.py:237,363,376,421`, nessuna correzione durante il test |

**Ripristino:** nessuno, sola lettura. **Superamento:** ricalcolo indipendente coerente con nota Safe e
frame Mike su tutte le partite campionate; `hazard_atlas_leghe` cresce per le leghe osservate.

#### 7.9.4 Catchup/quota: referto buchi e riserva dinamica ricalcolati

Fonte: `BACKFILL_AUTOMATICO_STAGIONI.md`, `CATCHUP_P4_STAGIONI_MAI_CARICATE.md` (interi).

| # | controllo | input dal DB/log e funzione di produzione importata (sonda, sola lettura) | confronto | criterio | se non torna (KO) |
|---|---|---|---|---|---|
| 7.9.4.B | il REFERTO BUCHI ricalcolato per 3 lega-stagioni a campione dà lo stesso numero del referto pubblicato; la riserva dinamica dichiarata (300/3000) corrisponde allo stato VERO delle 3 action su GitHub; il contatore API dichiarato corrisponde a `/status` reale | (a) 3 lega-stagioni a campione (almeno una con buchi noti, una «DB SENZA BUCHI»): `select * from public.season_detail_gaps(<league_id>, <season_year>, null);` (`migrations/season_gaps_2026-09-25.sql`); ricalcolo diretto: `select count(*) from public.matches m where m.league_id=<lid> and m.season_year=<sy> and m.status in ('FT','AET','PEN') and not exists (select 1 from public.match_events e where e.fixture_id=m.fixture_id);` (idem per `match_lineups`), scartando le righe con `fixture_detail_checks.esito in ('vuoto','parziale')` non ancora scadute come nella RPC; (b) `gh run list --workflow=daily_yesterday_backfill.yml --json status,conclusion,createdAt -L 5`, idem `today_predictions_backfill.yml` e `predictions_results_backfill.yml` (le 3 action vere, `.github/workflows/`) per il giorno UTC corrente; ricalcolo importando `seasons_catchup.action_completate_oggi` (`seasons_catchup.py:178`) e `api_quota.riserva_del_momento` (`api_quota.py:233`) con lo stato letto in (b); (c) chiamata `GET /status` di API-Football (stessa chiamata gratuita del catchup, `api_quota.py:86-103` `leggi_status_api`) | conteggio `da_chiamare`/`errore`/`da_richiamare` della RPC (a) contro il conteggio diretto sulle tabelle vere; riserva dichiarata nel log `[CATCHUP] quota all'avvio: ... riserva action N ...` contro `riserva_del_momento` ricalcolata dallo stato reale delle 3 action (b); contatore `N/7500` del log contro `response.requests.current/limit_day` di `/status` (c) | uguaglianza numerica esatta sui conteggi di buchi per le 3 lega-stagioni; riserva = 300 se e solo se le 3 action sono `success` dopo il loro cron di oggi e nessuna `in_progress`/`queued` (altrimenti 3000, con avviso se GitHub non leggibile); contatore = `current` di `/status` esatto | RPC che conta un buco diverso dal conteggio diretto, riserva dichiarata 300 con almeno una delle 3 action ancora `in_progress`/fallita oggi, o contatore diverso da `/status` = evidenza + `migrations/season_gaps_2026-09-25.sql`, `seasons_catchup.py:178`, `api_quota.py:87,233`, nessuna correzione durante il test |

**Ripristino:** nessuno, sola lettura (nessuna chiamata API a pagamento). **Superamento:** i 3 conteggi
coincidono, la riserva e il contatore ricalcolati coincidono col log del catchup.

#### 7.9.5 Schede B17 + esecuzione a mercato: cosa vede il trader, e a che prezzo parte davvero

Fonte: `SCHEDE_ABBINAMENTO_PREZZO.md`, `DRYRUN_E_ESECUZIONE_A_MERCATO.md` (interi).

| # | controllo | input dal DB/log e funzione di produzione importata (sonda, sola lettura) | confronto | criterio | se non torna (KO) |
|---|---|---|---|---|---|
| 7.9.5.D | ogni numero a video nella striscia B17 (prezzo al ms, banda, Δ tick, «ABBINATO…») è quello REALMENTE successo sul mercato, non un calcolo isolato lato UI | dopo un ordine paper/live: (a) testo esatto della striscia; (b) riga del bot: `select meta->>'prezzo_segnale', meta->>'prezzo_visto', meta->'esecuzione_al_clic', meta->'esecuzione' from safe_strategy_trades where id=<trade_id>;` (Omega: `omega_trades`; Mike: `mike_requests`/`mike_events`); (c) diario `_diario_ordini` per lo stesso `customerOrderRef` (righe `ordine`/`esito`); (d) ladder reale nello stesso istante (`_live_raw` o `safe_strategy_scan` allo stesso `updated_at`) | prezzo medio abbinato mostrato (a) contro `average_price_matched`/prezzo dell'esito (c); Δ tick mostrato ricalcolato con `riskMath.ticksBetween` sui prezzi salvati (b) e il prezzo eseguito (c); `meta.esecuzione_al_clic.prezzo_attuale` (b) contro il miglior prezzo della ladder nello stesso istante (d) | uguaglianza numerica esatta (prezzo, size, tick) fra quanto mostrato e quanto scritto su riga/diario, salvo arrotondamento del tick | prezzo/size mostrati diversi da riga/diario, o Δ tick calcolato male = evidenza (i 4 valori affiancati) + `frontend/src/lib/esitoAbbinamento.ts:349,484`, nessuna correzione durante il test |
| 7.9.5.C | al clic il prezzo REALMENTE chiesto è dentro la banda VERA calcolata dai parametri della strategia in quel momento, non una banda mostrata ma diversa da quella usata dal servizio | proposta Safe con `criteri`/`p_model`: `payload.criteri` della proposta + `select params from safe_strategy_control;`; ricalcolo importando `banda_della_strategia`/`in_banda` da `Betfair.safe_strategy.proposte_opportunita` (`:697,707`) con gli stessi `criteri`/`p_model`/params; confronto con `meta.esecuzione_al_clic.banda` sulla riga e col prezzo chiesto sull'ordine vero (`_prezzo_chiesto`, flumine) | banda Y-Z ricalcolata contro banda Y-Z scritta su `meta.esecuzione_al_clic.banda`; prezzo chiesto sull'ordine reale dentro [Y,Z]; fuori banda → riga `fuori_banda_strategia` e NESSUN ordine partito | uguaglianza esatta della banda calcolata; prezzo chiesto sull'ordine reale sempre dentro [Y,Z] quando l'ordine parte | banda ricalcolata diversa da quella scritta, o ordine partito con prezzo chiesto fuori dalla banda ricalcolata = evidenza + `proposte_opportunita.py:697,707`, `bot_service.py:2682-2725`, **money-critical, portare all'utente** |
| 7.9.5.E1 | clic con mercato SUSPENDED: mai un fill piazzato alla cieca, o si rifiuta o si attende la riapertura | clic durante una sospensione nota (osservata o, con permesso, costruita in test); esito della riga + log; ricalcolo `mercato_operabile` (`stato_mercato.py`) sullo stato registrato in `_live_raw` allo stesso istante | esito della riga contro `mercato_operabile(...)` ricalcolato | `mercato_operabile(...)[0] is False` → riga SEMPRE senza fill (attesa/rifiuto), mai un prezzo eseguito | fill con prezzo eseguito mentre il ricalcolo dà SUSPENDED = evidenza + `stato_mercato.py:11`, **STOP** |
| 7.9.5.E2 | prezzo che salta fra clic ed esecuzione (esecuzione al miglior prezzo di adesso, non al prezzo visto): il caso reale del replay (`fuori_banda_strategia` sulla registrazione 35759636) è riproducibile | rieseguire (permesso del coordinatore) `python -m Betfair.stream.backtest.certifica safe_base --scenari proposta-approvata --worker 1 --data-dir <repo>/_live_raw` sulla registrazione 35759636 (già in `AUDIT_2026-09-25/replay_safe_proposta_approvata_d7_35759636.txt`); esito PM3 (`Betfair/stream/backtest/proposte_modello.py`, `_banda`/`_pm3_banda`) | esiti dichiarati dal replay (1 ok, 1 `fuori_banda_strategia`, 1 `non_eseguito` FOK) contro un rilancio indipendente dello stesso scenario | stessi esiti, stesso numero di violazioni (0), stesso motivo sulla stessa approvazione | esiti diversi dal referto pubblicato sulla stessa registrazione = regressione PM3/banda, evidenza + `proposte_modello.py`, nessuna correzione durante il test |
| 7.9.5.E3 | FOK non abbinato: quando il miglior prezzo non copre l'intera size, il FOK muore SENZA fill parziale inventato | caso `paper_fok_parziale`/`paper_no_fill`/`live_not_matched:EXPIRED` in log/attività; riga (`size_matched`, `avg_price_matched`) + book reale nello stesso istante (`_live_raw`) | `size_matched` della riga (0/assente) contro la size disponibile al miglior prezzo nel book reale contro la size richiesta | size disponibile al miglior prezzo < size richiesta → SEMPRE «NON abbinato (FOK)», `size_matched` mai un fill fittizio | riga con `size_matched` > 0 mentre il book reale non copriva l'intera size al prezzo richiesto = fill inventato, evidenza + `esitoAbbinamento.ts` (blocco FOK), **STOP, money-critical** |

**Ripristino:** nessuno per D/E1/E3 (sola lettura); E2 è un replay dichiarato senza scritture (permesso
del coordinatore). **Superamento:** le 5 voci passano, nessun numero a video divergente dal DB/diario,
nessuna banda calcolata diversa da quella scritta.

#### 7.9.6 Scalper e tennis auto-mode: armate = idonee del feed, casi subdoli

Fonte: `SCALPER_AUTO_MODE.md`, `TENNIS_AUTO_MODE.md`, `TENNIS_AUTO_FOLLOW.md` (interi). **Nota per il
coordinatore prima della fase 2**: `AUTO_FOLLOW_TUTTI_I_BOT.md` §6 dichiara «tennis NON fatto, buco
dichiarato» (nessuna iscrizione a caldo), mentre `TENNIS_AUTO_FOLLOW.md` (stesso giorno, delegato
diverso) descrive `Betfair/stream/tennis_live/iscrizione_a_caldo.py` come GIÀ scritto e testato (46 test
verdi, 22/22 mutazioni rosse). I due referti si contraddicono: 7.9.6.E3 verifica PRIMA di tutto quale
versione è davvero su master per la fase 2.

| # | controllo | input dal DB/log e funzione di produzione importata (sonda, sola lettura) | confronto | criterio | se non torna (KO) |
|---|---|---|---|---|---|
| 7.9.6.B | le partite armate in automatico (`origine='auto'` su `scalper_control`/`tennis_bot_control`) sono ESATTAMENTE quelle idonee secondo il feed nello stesso istante, nell'ordine atteso, dentro il tetto | righe vere del feed nello stesso istante: `select event_id, sport, updated_at, payload from safe_strategy_scan where sport='calcio' and updated_at > now()-interval '30 seconds';` (scalper) e `sport='tennis'` (tennis); ricalcolo importando `Betfair.stream.scalper.auto_mode.partite_dal_feed` (`:183`) e `Betfair.stream.tennis_live.auto_mode.partite_dal_feed`+`scegli_partite` (`:137,177`) con le stesse righe e lo stesso tetto; righe realmente armate: `select event_id, origine, status from scalper_control where origine='auto';` e `select bot_key, event_id, status from tennis_bot_control where origine='auto';` | insieme (`event_id`) del ricalcolo contro l'insieme realmente armato; ordine (priorità/FIFO) del ricalcolo contro l'ordine osservato nel log | uguaglianza insiemistica esatta entro il tetto (nessuno in più né in meno); stesso ordine di scelta a parità di tetto | partita idonea nel ricalcolo mai armata, o partita armata che il ricalcolo esclude = evidenza (le due liste affiancate) + `auto_mode.py:183` (scalper), `auto_mode.py:137,177` (tennis), nessuna correzione durante il test |
| 7.9.6.E1 | partita che sparisce dal feed: sessione/bot fermato in modo pulito, senza chiudere di scatto una posizione viva | partita fuori dal feed da ≥60 s con sessione/bot `origine='auto'` ancora attivo; `select event_id, status, origine from scalper_control where origine='auto';` / `tennis_bot_control` nei minuti seguenti | stato prima/dopo l'uscita dal feed, e presenza di posizioni vive nel frattempo | senza posizioni → `stopping`/`stopped` entro il tempo dichiarato (~60-75 s scalper, grazia tennis di serie); CON posizioni → resta finché non è flat, mai un flatten forzato | sessione ferma con posizione viva ancora aperta, o sessione armata a tempo indefinito su feed morto = evidenza + `Betfair/stream/scalper/auto_mode.py:307` (`da_fermare_per_feed`), `Betfair/stream/tennis_live/iscrizione_a_caldo.py` (grazia uscita), nessuna correzione durante il test |
| 7.9.6.E2 | scanner fermo (battito > 30 s): NESSUNA nuova partita armata; la nota dichiara la causa vera | battito vecchio (`safe_strategy_status`, osservato o, con permesso, simulato in test); nota a video/log del bot scalper/tennis | nota dichiarata contro lo stato vero del battito (`_SCANNER_VIVO_S`/`SCANNER_ALIVE_MAX_AGE_SEC`) | nota = «feed … non disponibile (scanner fermo o lettura KO)» col battito vecchio, mai un armamento nuovo in quella finestra | armamento con scanner vecchio, o nota generica senza causa = evidenza + `Betfair/stream/scalper/auto_mode.py:350` (`motivo_blocco`), `Betfair/stream/tennis_live/auto_mode.py:233`, nessuna correzione durante il test |
| 7.9.6.E3 | bot tennis con posizione VIVA + partita NUOVA nel feed («tennis a caldo»): PRIMA verificare quale versione è su master (vedi nota sopra), poi che la posizione viva non impedisca né sia messa a rischio dall'ingresso della partita nuova | grep `iscrizione_a_caldo` sul ramo di fase 2 (presenza del modulo e dell'interruttore `TENNIS_ISCRIZIONE_A_CALDO`); con un bot in posizione e una partita nuova nel feed: `select event_id, status from tennis_live_follow where origine='auto';` + log `[tennis] iscrizione a caldo ...` (o assenza) | se integrato: entrata della partita nuova SENZA restart (stesso `framework_gen`), ricalcolo di `iscrizione_a_caldo.pianifica` (`:161`) con le priorità vere (posizioni vive mai espulse) contro l'ordine osservato; se NON integrato: la nota deve dichiarare il buco, mai un silenzio | con `iscrizione_a_caldo` attivo: `framework_gen` invariato, partita nuova streaming entro pochi secondi, posizione del bot vecchio intatta; senza: nessuna perdita di posizione E la mancata copertura è dichiarata | posizione persa o `framework_gen` che cambia con una posizione viva = evidenza + `iscrizione_a_caldo.py:25` (tabella prima/dopo), `tennis_runner.py:930,1653,1669`, **STOP, money-critical**; oppure una copertura data per «fatta» in un referto ma assente su master = divergenza fra i due referti del 25/09, va scritta e portata all'utente PRIMA della fase 2 |

**Ripristino:** nessuno per B/E2 (sola lettura); E1 osservato dal vivo senza azioni; E3 è
un'osservazione, nessuna scrittura. **Superamento:** le 4 voci passano E la divergenza fra i due referti
sull'iscrizione a caldo tennis è stata risolta (quale versione è vera) prima di dare torto/ragione a E3.

#### 7.9.7 Safe: checklist delle condizioni contro il feed dello stesso istante

Fonte: `SAFE_Q1_Q4_Q5.md`, `SAFE_DECISIONI_D5.md` (interi).

| # | controllo | input dal DB/log e funzione di produzione importata (sonda, sola lettura) | confronto | criterio | se non torna (KO) |
|---|---|---|---|---|---|
| 7.9.7.C | per OGNI ingresso ed OGNI mancato ingresso Safe, la checklist (banca 20-34, veto finali dal round, femminile, h2h dal DB, super sfavorito < 1,20, minuti, bande pre-partita, un solo ingresso per partita, ingresso prima dell'uscita) confrontata col feed dello stesso istante dà lo stesso esito scritto, e il motivo di scarto è la condizione VERAMENTE violata | per 5-10 candidati osservati (mix ingressi/scarti): (a) riga del feed nello stesso istante (`safe_strategy_scan`); (b) params veri (`select params from safe_strategy_control;`); (c) h2h dal DB per la coppia di squadre; (d) `select payload->>'motivo', payload->>'event_id', ts from safe_strategy_activity where kind in ('scartata','ingresso') order by ts desc limit 20;`; ricalcolo importando `Betfair.safe_strategy.veto_campionati.voce_vietata`/`squadra_femminile`/`is_round_finale`/`nome_indica_finale` (`veto_campionati.py:128,161,196,222`), `Betfair.safe_strategy.selezione.conta_scontri_diretti` (`:281`), `Betfair.safe_strategy.engine.tennis_sfavorito_estremo_check` (`:1013`) e `Betfair.safe_strategy.engine.selection_check` (`:909`, banca 20-34 e condizioni base), tutte chiamate con gli stessi input (a)-(c) | esito/motivo di ciascuna funzione ricalcolata contro (i) se il candidato è entrato o no, (ii) il motivo scritto in (d); per gli ingressi TUTTE le condizioni ricalcolate devono risultare «passa»; per gli scarti ALMENO la condizione citata nel motivo deve risultare «viola» | uguaglianza esatta fra esito ricalcolato e decisione reale; il motivo scritto cita la stessa condizione che il ricalcolo indica come violata | ingresso dove il ricalcolo trova una condizione violata (banca fuori 20-34, femminile non riconosciuto, h2h che avrebbe dovuto scartare, sfavorito estremo non escluso) = evidenza + `veto_campionati.py:115-222`, `selezione.py:281`, `engine.py:909,1013`, **STOP, si scrive e si porta all'utente**; motivo di scarto che non corrisponde alla condizione realmente violata = difetto di trasparenza, stessa evidenza richiesta |

**Ripristino:** nessuno, sola lettura. **Superamento:** su tutti i candidati campionati, decisione ed
esito ricalcolato coincidono, e il motivo scritto è sempre quello vero.

---

## 8. Punti «da verificare» (non li ho potuti confermare dal codice)

1. Come servire la UI con app spenta (§1.6): serve il permesso dell'utente; login Supabase da `localhost:4173`.
2. Sonda di lettura (§1.7): nessun effetto collaterale all'import di `bot_service`, `tennis_bot_service`,
   `scalper_service`; `db_client` legge il `.env` come i servizi.
3. Elenco completo dei CHECK di stato delle code (`processing` ecc.) sullo schema vivo.
4. Chiavi esatte scritte da `extraSoloTennis` (P15) in `components/controlroom/soloTennis.ts` (non riletto).
5. `omegaParamsPatch` della pagina Omega (P06): che non tolga chiavi.
6. Chiave dell'ultimo giro nei push `omega_stato`/`safe_stato` (`stats.last_cycle`?) (Z4.O1).
7. Valore esatto di `hazard_versione` per il v4 in `mike_events.live` (Z4.M2) e dove finisce la nota hazard di Safe
   (attività o `meta` della proposta) (Z4.S4).
8. Colonne di `betfair_live_heartbeat` (Z2.1) e di `hazard_atlas_leghe` (Z10).
9. Colonna del ref interno negli ordini dello specchio (Z4.S5).
10. Dove finisce oggi la console dell'app, per `leggi_tempi_ordine` (Z5; referto F0 §7).
11. ~~Quale job/processo rigenera i payload TacticAI dopo `43e1468` (Z8).~~ **Risolto:** action
    `today_predictions_backfill` → `Prediction/today_predictions_backfill.py:2741-2746` → `tactical_engine.serving.run_for_date`.
12. Stato di applicazione di `get_direction_eta_2026-09-25.sql` e `market_delays_ht_2026-09-25.sql` (§1.1).
13. ~~Comportamento del kill-switch sulle aperture PAPER di Mike e dello scalper calcio (Z13.4): dal codice NON li
    ferma; da confermare dal vivo e portare all'utente.~~ **Risolto (chiuso col fix, non più da verificare a
    parte):** con `6ac2543` (R3) il freno È UNICO e ferma anche Mike e lo scalper calcio, in paper come in live
    (vedi Z13.4, P27). Resta da CONFERMARE dal vivo in fase 2 (non più «da portare all'utente» come reperto
    aperto: è già un fix applicato, la fase 2 lo certifica).
14. **[coordinatore]** Se `migrations/uscite_manuali_default_2026-09-25.sql` (§1.1) risulti già applicata al
    momento del test: da controllare con le query della riga stessa PRIMA di avviare la fase 2.
15. **[coordinatore]** Se, dopo l'avvio nuovo dell'app, un residuo `tennis_bot_service_control.status='stopping'`
    del 24/09 sia stato davvero ripreso a `stopped`/`paper` dal fix R2 (Z0.2bis): il coordinatore riporta oggi
    sul DB una riga così residua, non ancora passata da un avvio con `6ac2543` in produzione.

## 9. Reperti emersi scrivendo il piano (da portare all'utente, nessuna correzione fatta)

- **R1 — tennis per partita:** il confirm dice «ORDINI REALI», la RPC scrive sempre `mode='paper'` (P21).
- **R2 — tennis all'avvio — CHIUSO (commit `6ac2543`, 25/09 sera):** era «gli interruttori tornano `stopped` ma
  la `mode` NON torna `paper` (P19), a differenza di Omega/Mike/Safe/scalper». Ora `ferma_interruttori_al_nuovo_avvio`
  (`tennis_bot_service.py:806-855`) scrive `status='stopped'` **E** `mode='paper'` per i 4 bot, come gli altri.
  Resta da confermare dal vivo che un residuo `stopping` di PRIMA del fix venga ripreso al prossimo avvio nuovo
  (§8 punto 15, Z0.2bis) — non è più una divergenza di comportamento, è la fase 2 che lo certifica.
- **R3 — kill-switch — CHIUSO (commit `6ac2543`, 25/09 sera, «freno unico»):** era «non ferma le aperture paper
  di Mike né lo scalper calcio (Z13.4); non ha una riga in Control Room (P27)». Ora il freno è UNICO (ferma ogni
  apertura, live e paper, di tutti i bot: Safe, Omega, Mike, scalper) e ha una riga dedicata in Control Room
  (`RigaFreno.tsx`, accanto a «Ordini reali»), oltre al punto storico in Segui Live. Vedi Z13.4 e P27 aggiornati.
- **R4 — replay:** nessun replay completo sui cambi del 25/09 (§0.5).

**Altre decisioni della sera del 25/09 verificate contro questo piano (coordinatore):** aiuti statistici O1/O5/M1
accesi di default (`lambda_quote_prima`, `model_red_cards`, `veto_p_under35_cal`, commit `931c11b`), sniper mode
dello scalper acceso di default (`auto_mode.sniper_mode_acceso`, commit `fae8ce1`), moduli di laboratorio fuori da
`Betfair/` (`laboratorio/scalper_lab`, `laboratorio/tennis_lab`, commit `4021453`) — **nessuna riga di questo piano
le contraddice**: nessuna sezione le dava per spente/dentro `Betfair/`, quindi non serve correzione, solo la
conferma che restano valide per il test.

## 9-bis. KO candidati noti prima del test (da confermare in fase 2/3, NON corretti)

Trovati leggendo il codice per scrivere questo piano (coordinatore, 25/09 sera). Sono KO CANDIDATI, non
KO certi: vanno confermati dal vivo in fase 2/3 con l'evidenza indicata, e portati all'utente — **non si
corregge il codice per farli sparire durante il test** (CLAUDE.md, regola generale).

1. **P&L per bot (`cr-bot-pnl-<id>`) sempre NULL per Omega/Safe/Mike.** `PannelloBot.tsx:596 data-testid="cr-bot-pnl-${r.id}"`
   mostra `pnlOggi`; ma in `frontend/src/components/controlroom/useControlRoom.ts:2236-2238` la funzione `riga(...)`
   scrive `pnlOggi: isBotTennis(bot) ? pnlTennisDi(...) : null` — per `bot` in `('omega','safe','mike')` questo è
   **sempre `null`** (solo i 4 bot tennis e lo scalper, quest'ultimo a parte a `:2358`, hanno un valore). **Cosa si
   vede:** la riga di Omega/Safe/Mike in Control Room mostra sempre il trattino al posto del P&L di oggi. **Come
   si conferma:** in fase 2, con un trade paper regolato su uno dei tre bot, verificare che `cr-bot-pnl-omega`
   (o safe/mike) resti `—` mentre il DB ha righe `settled` col `pnl` valorizzato.
2. **Paper e live sommati a video col filtro «tutte».** `frontend/src/pages/LivePnl.tsx:192,269,272`: `modeF`
   può essere `'all'`, e con `'all'` il filtro `s => modeF === 'all' || s.mode === modeF` (`:269`) NON esclude
   nulla — `realized` (`:272`) somma `profit` su TUTTE le righe, paper e live insieme. In Market Watch, la
   tessera «Rischio» (`MarketWatch.tsx:354-356`, `eventExposure(positions)`) usa `get_live_positions_event`
   (`migrations/betfair_live_pnl_journal.sql:258-280`), che NON filtra per `mode`, e `eventExposure`
   (`frontend/src/lib/eventPnl.ts:68-75`) somma `selection_exposure` su tutte le righe passate, senza distinguere
   modalità. **Cosa si vede:** con filtro «tutte» selezionato, il numero mostrato non è la somma dichiarata di
   UNA modalità. **Come si conferma:** in fase 2 (tutto paper, quindi il caso non si manifesta da solo), verificare
   col codice/con una riga `live` residua storica se presente che il numero con filtro «tutte» ≠ somma dei soli
   `mode='paper'`.
3. **Le tessere Calcio/Tennis della Control Room mostrano solo il P&L di Safe.** `useControlRoom.ts:3480`
   `perSport: safeOggi?.by_sport ?? null` (commento a `:3483-3484`: «QUI C'ERANO I CONTATORI DI `get_safe_daily`,
   che legge la SOLA tabella di Safe»): il componente `SplitSport.tsx` («due entità, calcio e tennis») riceve dati
   SOLO da `get_safe_daily`, non un aggregato di Omega/Mike/scalper/tennis sullo stesso sport. **Cosa si vede:**
   le tessere ⚽/🎾 in Control Room non includono il contributo di Omega (calcio), Mike (calcio), scalper (calcio)
   né dei 4 bot tennis. **Come si conferma:** in fase 2, con Omega o Mike che regola un trade calcio, verificare
   che la tessera Calcio NON si muova per quel trade.
4. **Safe (pagina dedicata) senza fonte/età del canale 47335 a video.** `frontend/src/pages/Omega.tsx:511-518`
   ha il badge `data-testid="omega-canale-locale"` («Canale LOCALE attivo (ws://127.0.0.1:47334)…»);
   `frontend/src/pages/Mike.tsx:384-391` ha l'equivalente `data-testid="mike-canale-locale"` (ws 47333).
   `frontend/src/pages/SafeStrategy.tsx` NON ha alcun badge equivalente (nessuna occorrenza di
   `canaleLocale`/`canale-locale`/`47335`/`ws://127`). **Cosa si vede:** sulla pagina Safe dedicata non c'è modo
   di sapere se i numeri di testata arrivano dal canale 47335 o dal ripiego DB, a differenza di Omega/Mike. **Come
   si conferma:** aprire `/safe-strategy` in fase 2 e verificare che manchi un badge equivalente a quello di
   Omega/Mike (la Control Room, invece, il fonte/età di Safe ce l'ha: `ControlRoom.tsx:1143-1147
   cr-bot-fonte-safe` — il buco è solo sulla pagina dedicata).
5. **5 topic pubblicati sui canali che la UI non legge mai (0 occorrenze in `frontend/src`, test compresi):**
   `mike_attivita` (pubblicato `Betfair/mike/db.py:78`), `omega_attivita` (`Betfair/omega/omega_db.py:67`),
   `safe_attivita` (`Betfair/safe_strategy/bot_db.py:83`), `tennis_bot_armamento`
   (`Betfair/stream/tennis_live/tennis_db.py:222,362,636`), `auto_follow` (`Betfair/stream/runner.py:1703`,
   §7.2). **Cosa si vede:** questi 5 topic viaggiano sul canale locale del processo ma nessun componente
   frontend li sottoscrive: l'unico modo di vederne l'effetto oggi è il DB (poll) o i log, mai un push realtime
   dedicato. **Come si conferma:** durante la fase 2, con l'auto-follow attivo (§7.2), verificare che non ci sia
   nessuna sottoscrizione realtime a questi 5 topic in nessuna pagina aperta (Network/WS del browser).
6. **`scalper-service` e il ponte tennis (`tennis-bot-service --bridge-only`) senza watchdog.** `desktop/main.js:288,289,304,311,317,322`
   avviano runner-calcio, runner-tennis, safe-strategy-service, omega-service, safe-strategy-bot, mike-service
   tutti dentro `-m Betfair.stream.watchdog -- <modulo>`; `desktop/main.js:292`
   (`spawnRunner('scalper-service', ['-m', 'Betfair.stream.scalper.scalper_service'])`) e `:298`
   (`spawnRunner('tennis-bot-service', ['-m', 'Betfair.stream.tennis_live.tennis_bot_service', '--bridge-only'])`)
   sono lanciati SENZA il wrapper watchdog. **Cosa si vede:** se il processo dello scalper o il ponte tennis
   crashano, nessun riavvio automatico (a differenza degli altri sei processi); i bot tennis/scalper restano
   fermi finché l'utente non riavvia l'app. **Come si conferma:** non provocabile in modo pulito durante il
   test (andrebbe ucciso un processo); da segnalare come reperto, eventualmente verificabile a parte se
   l'utente lo autorizza.
7. **L'action Poisson settimanale committa `Betfair/money_management.py`.** `.github/workflows/weekly_poisson_calibration.yml:38,60,67-70,76`:
   `git add dynamic_cal.json Betfair/money_management.py dc_rho_by_league.json` seguito da `git commit`/`git push`
   automatici. **Cosa si vede:** un file di codice della strategia (non solo dati) viene scritto e pubblicato da
   un'action schedulata, senza revisione umana per singola modifica. **Come si conferma:** `git log -- Betfair/money_management.py`
   mostra commit automatici dell'action; da portare all'utente (le strategie non si alterano di iniziativa,
   CLAUDE.md) — non è un bug del test e2e, è una policy da rivedere.
8. **3 RPC vivono in `sql/`, non in `migrations/`.** `sql/leagues_needing_retrain_rpc.sql`,
   `sql/market_delays_rpc.sql`, `sql/market_frequency_rpc.sql` (più `sql/perf_indexes.sql`, indici non RPC).
   **Cosa si vede:** queste 3 funzioni non passano dal punto d'ingresso unico `migrations/` che il resto del
   piano usa per «applicata/da applicare» (§1.1): non c'è modo di sapere se sono applicate sul DB vivo dalla
   stessa fonte usata per tutto il resto. **Come si conferma:** `select proname from pg_information_schema...`
   o `pg_get_functiondef` sulle 3 firme, confrontato col contenuto dei file in `sql/`.
9. **`LIVE_ORDER_QUEUE_POLL_SEC` ha DUE default diversi nel codice, e l'app ne passa un terzo.**
   `Betfair/order_worker.py:26`: `float(os.getenv("LIVE_ORDER_QUEUE_POLL_SEC", "2"))`;
   `Betfair/stream/config_stream.py:223`: `float(os.getenv("LIVE_ORDER_QUEUE_POLL_SEC", "1.0"))`;
   `desktop/main.js:233`: l'app imposta sempre `LIVE_ORDER_QUEUE_POLL_SEC: '0.15'` nell'ambiente dei processi
   figli. **Cosa si vede:** col `.env` passato dall'app il valore vero è sempre `0.15` (Z5 già lo usa come
   riferimento); MA uno script/tool lanciato fuori dall'app (a mano, senza l'ambiente di `main.js`) userebbe `2`
   o `1.0` a seconda del modulo che legge la env — due «verità» diverse per lo stesso nome. **Come si conferma:**
   non è un guasto della fase 2 (l'app imposta sempre `0.15`); da portare all'utente come pulizia di codice (un
   solo default, in un solo posto).

## 10. Fonti lette (sola lettura)

`CLAUDE.md`; `PROCESSO_STANDARD_BOT.md` §6-§7; `HANDOFF_CONTROL_ROOM.md` (indice); `CRONOSTORIA.md` sezioni 24/09
(parziale) e 25/09 (intera); `AUDIT_2026-09-24/AUDIT_MODALITA_PAPER_LIVE`, `AUDIT_STRADE_ORDINE` §0-2 e §6,
`AUDIT_TEMPO_REALE` §0-1; `AUDIT_2026-09-25/`: `F0_TEMPI_ORDINE`, `USCITE_AUTOMATICHE_PER_BOT`, `TENNIS_AUTO_MODE`,
`SCALPER_AUTO_MODE`, `O2_TRANSIZIONI_OMEGA`, `TACTICAI_P00_NEGATIVA` (§1-2), `ATLANTE_V4_COLLEGATO`,
`AUDIT6_TEMPO_REALE` (voci 4-14), `SCHEDE_ABBINAMENTO_PREZZO` §1-2, `SAFE_Q1_Q4_Q5` §1-2, `BACKFILL_AUTOMATICO_STAGIONI`
(ricerca mirata). Codice e migrazioni citati riga per riga sopra. **Non letti per intero:** `F10A_CONTRATTO_STRADA_UNICA`,
`STRADA_UNICA_BANCO_E_PAPER`, `MISURA_PUNTO8`, `VALIDAZIONE_HAZARD`, `AUDIT3_*`, `AUDIT5_TACTICAI_TAB`,
`FIX_CIRCOSCRITTI_F1_F4`, `PREPARAZIONE_O1_M1`, `ACTIONS_DIAGNOSI_E_FIX`, `ATLANTE_TUTTE_LE_LEGHE`, `BACKFILL_TRE_CHIUSURE`
(solo citati tramite la cronostoria).

---

## Esiti fase 1 (admin-26)

Eseguita dal delegato del coordinatore (Sonnet 5, worktree isolato, rebase su
`origin/master` `d771d05` ≥ `099412c`), 25/09/2026, SOLA LETTURA: sonde REST
PostgREST dirette (`select`/`limit` espliciti, RPC solo se esposte in GET/`STABLE`),
introspezione OpenAPI (`GET /rest/v1/`), `.env` del checkout principale (chiavi
segrete mai stampate), `gh run view --log` sull'ultimo run reale di
`seasons_catchup.yml`, un dry-run REALE di `python league_orchestrator.py --league
135 --season 2026 --dry-run` (exit 0, nessuna scrittura, nessuna chiamata API a
pagamento), e 288 test `pytest` GIA' esistenti nel repo rieseguiti ora (nessuna
scrittura, mock propri). Referto completo, riga per riga, con evidenza per ognuno dei
65 controlli 7.1-7.8: `AUDIT_2026-09-25/E2E_FASE1_ADMIN26.md`.

| Sottosezione | PASS | FASE 2 | FAIL |
|---|---|---|---|
| 7.1 Feed unico | 0 | 4 | 0 |
| 7.2 Auto-follow e strada unica ordini | 1 | 12 | 0 |
| 7.3 Atlante v4 | 4 | 4 | 0 |
| 7.4 Catchup e referto buchi | 8 | 0 | 0 |
| 7.5 Schede B17 | 6 | 2 | 0 |
| 7.6 Scalper auto-mode | 3 | 5 | 0 |
| 7.7 Tennis auto-mode | 6 | 2 | 0 |
| 7.8 Safe: veti aggiuntivi | 8 | 0 | 0 |
| **Totale** | **36** | **29** | **0** |

**Nessun FAIL.** Tre note di trascrizione nel piano (non difetti del codice, dettaglio
nel referto): (1) §7.4.8 cita un modulo `Betfair.stream.backfill.league_orchestrator`
inesistente — lo script vero è `league_orchestrator.py` in radice, eseguito con
successo; (2) §7.3.5 cita `dossier.py:309-321`, le chiavi si scrivono a 340-342 dello
stesso file; (3) §7.5.1 cita `bot_service.py:2778`, la scrittura vera è a 2825-2827
dello stesso file.

**Fatto rilevante emerso, non un difetto ma da sapere prima della fase 2:**
`hazard_atlas_leghe` è **vuota** (0 righe) — nessuna lega ha ancora uno stato v4
scritto; nessuna tabella di follow (`scalper_control`, `live_follow`,
`tennis_live_follow`) ha righe `origine='auto'` — l'auto-mode non è mai stato
esercitato dal vivo su questo DB. La fase 2 su questi fronti (7.1, 7.2, 7.3.3, 7.3.5-6,
7.6, 7.7.4/7.7.8) parte da zero, coerente con l'attivazione odierna delle funzioni.

I 29 controlli **FASE 2** (elenco id nel referto completo) restano da rifare con l'app
accesa, nella stessa forma già scritta dal piano in §7.1-§7.8; il valore atteso è
quello già scritto lì per ciascuno, non alterato da questa sessione.
