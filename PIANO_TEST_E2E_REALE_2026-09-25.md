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
```

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
- **Ripristino:** valore della fotografia (default assente = `true`).

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
- **Ripristino:** ferma → §5.1. **Nota:** a un avvio nuovo il ponte riporta a `stopped` SOLO lo `status`, NON la
  `mode` (`tennis_bot_service.py:799-846`, `set_tennis_bot_service_state` `tennis_db.py:550-573` non scrive `mode`):
  il test lascia la `mode` a `paper` a mano (§5.1). **Reperto da portare**: diverso da Omega/Mike/Safe
  (`avvio_app.py:212-220` scrive `mode='paper'`). Non pericoloso oggi perché ogni accensione riscrive la modalità
  (`avviaBot` la passa sempre), ma è un'asimmetria.

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

#### P27 — Kill-switch (freno globale)
- **UI (NON è in Control Room):** pagina Segui Live → `LiveControlsPanel` (`frontend/src/pages/SeguiLive.tsx:857`,
  `components/live/LiveControlsPanel.tsx:137-160`): attivazione SENZA conferma, disattivazione con `window.confirm`;
  scorciatoia `Esc` in Segui Live (`SeguiLive.tsx:451-460,476`, con `window.confirm` in attivazione).
- **Codice/RPC:** `liveOrders.ts:683-688 setKillSwitch` → `set_live_kill_switch(p_on)` —
  `migrations/betfair_live_controls.sql:85-110`.
- **Riga attesa:** `betfair_live_settings.kill_switch=true`, poi `false`; `order_mode` INVARIATO.
- **Servizio:** `trading/controls.py:107 motivo_kill_switch` (env + DB, cache 2 s) → S-ORDINI stampa
  `db_kill_switch_attivo`; worker `live_order_worker.py:3576-3580` (ciclo), `:3622-3633` (per riga: apertura
  rifiutata, chiusura servita), canale `:3346-3349`; tennis `guardie_tennis.py:236,281-294`.
- **Ripristino:** `false` (confermando il dialogo). **Reperto per l'utente:** il kill-switch non ha una riga in
  Control Room (solo Segui Live): da decidere se serve lì.

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
| Z0.2 | tennis: `ripresa_ponte` (`tennis_bot_service.py:849-868`) ferma righe per partita e interruttori di un avvio vecchio; runner tennis `guardie_tennis.py:317 ripresa_all_avvio` | tutti i `tennis_bot_service_control` `stopped` (mode invariata, vedi P19); nessuna `tennis_bot_control` attiva | query §1.5 | righe attive = guardia del ponte non riuscita (log `[tennis-bot-svc] controllo d'avvio del ponte NON riuscito`) |
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
  → `negativi = 0`. Chi rigenera i payload (action o processo) è **da verificare**.
- **Se non torna:** negativi > 0 dopo il fix = il run non usa il codice nuovo o il fix non copre la previsione.

### Z9 — Catchup e quota API

- **Atteso:** `gh run list --workflow seasons_catchup.yml -L 3` verde; nel log il **REFERTO BUCHI**
  (`seasons_catchup.py:318-379`) con il conto delle lega-stagioni aperte in calo rispetto a 961 (25/09 h19:20);
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
| Z13.4 | kill-switch lascia passare solo le chiusure | con posizioni paper aperte: kill-switch ON (P27) → attendere un'apertura → OFF | coda calcio: aperture `error` «kill-switch ATTIVO: apertura RIFIUTATA», chiusure servite (`live_order_worker.py:3622-3633`); tennis: `TENNIS_KILL_SWITCH` rifiuta le aperture (`guardie_tennis.py:281-294`); **Mike paper e scalper calcio: dal codice il freno NON li ferma** (Mike: freno solo sulle aperture REST/appoggiate live, `mike/service.py:1219-1230`; scalper: solo il file `STOP_SCALPER`, `scalper_service.py:13,41`) | se Mike/scalper aprono col freno tirato: è il comportamento del codice → **reperto da portare all'utente** (non un guasto del test) |
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
```
Poi P32 (diff con la fotografia). Se `params` differisce, si rimette la colonna della fotografia **per intero**
(`update ... set params = '<json fotografato>'::jsonb`) — è l'unico caso in cui si riscrive `params`.

Rete di sicurezza (non sostituisce il ripristino): al primo avvio NUOVO dell'app Omega/Mike/Safe tornano
`stopped/paper` (`avvio_app.py:212-220`), il ponte tennis ferma gli interruttori (`tennis_bot_service.py:799-846`,
senza toccare `mode`), lo scalper ferma l'interruttore (guardia `scalper-auto`), `order_mode` scende a `paper`.

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
| kill-switch in Control Room | non esiste (solo Segui Live): da decidere, non da testare |
| stop giornaliero del tennis (E34) | decisione dell'utente del 25/09 h17:15: resta com'è |
| forza pre-partita nell'atlante v4 | non collegata (servono id squadra): decisione dell'utente |
| scanner/Betfair sotto carico, riconnessioni, 10 connessioni per app key | non provocabili senza toccare il sistema in esercizio |

---

## 7. Spazio per la sessione admin-26 (da riempire)

### 7.1 Feed unico
### 7.2 Auto-follow degli eventi dei bot (decisione D-1)
### 7.3 Atlante v4
### 7.4 Catchup e referto buchi
### 7.5 Schede B17
### 7.6 Scalper auto-mode
### 7.7 Tennis auto-mode

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
11. Quale job/processo rigenera i payload TacticAI dopo `43e1468` (Z8).
12. Stato di applicazione di `get_direction_eta_2026-09-25.sql` e `market_delays_ht_2026-09-25.sql` (§1.1).
13. Comportamento del kill-switch sulle aperture PAPER di Mike e dello scalper calcio (Z13.4): dal codice NON li
    ferma; da confermare dal vivo e portare all'utente.

## 9. Reperti emersi scrivendo il piano (da portare all'utente, nessuna correzione fatta)

- **R1 — tennis per partita:** il confirm dice «ORDINI REALI», la RPC scrive sempre `mode='paper'` (P21).
- **R2 — tennis all'avvio:** gli interruttori tornano `stopped` ma la `mode` NON torna `paper` (P19), a differenza di
  Omega/Mike/Safe/scalper.
- **R3 — kill-switch:** non ferma le aperture paper di Mike né lo scalper calcio (Z13.4); non ha una riga in
  Control Room (P27).
- **R4 — replay:** nessun replay completo sui cambi del 25/09 (§0.5).

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
