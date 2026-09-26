# E2E REALE — FASE 2, Z0: APP ACCESA, BOT FERMI (+ ciò che si certifica senza bot) — 26/09/2026

Delegato Opus del coordinatore (sessione B), worktree `agent-abc0f71d6f5ece18a`, base `origin/master` = `46e619b`
(`git fetch` alle 11:00: nessun commit più recente). **SOLA LETTURA**: nessuna scrittura sul DB, nessun comando ai
bot, nessun clic, nessun processo avviato o fermato (salvo le mie sonde brevi di lettura, elencate in §8), nessun commit.
Evidenze: `AUDIT_2026-09-25/e2e_fase2_z0/`. Orari: locale = UTC+2.

**Linea del tempo.** App avviata 10:56:41 (exe portable 1.1.0, pid 15624; `APP_BOOT_ID` = `mui5odst-…`, base 36 →
10:56:47,069 locali = avvio del processo principale 14708). Le letture «nessun bot opera» sono delle **11:02:50**
(09:02:50 UTC), i canali letti 11:05:30-11:06:30: **PRIMA dell'accensione**. Accensione in paper fatta dall'altro
delegato (`AUDIT_2026-09-25/e2e_fase2/ACCENSIONE_ORA.txt`): Omega 11:10:26, Mike 11:11:56, Safe 11:13:20 (+11:16:16),
4 tennis 11:16:50-58, scalper ~11:18. Tutto ciò che è letto dopo le 11:10 è marcato «dopo l'accensione».

**Esito sintetico.** Z0 (nessun bot opera) **OK** su tutte le righe, Z0.2bis **OK** (lo `stopping` del 24/09 è
sparito: R2 `6ac2543` funziona), processi e porte **tutti presenti**, canali 47331-47338 tutti vivi, scanner fresco
(p95 età 82 ms sul canale), atlante a domanda **vivo** (3 giri, 20 leghe v4). **4 KO/reperti nuovi** da portare
all'utente (K1 size del feed in sterline, K2 console dell'app non salvata → F0 non misurabile, K3 auto-follow calcio
proattivo inerte con le porte-canale spente, K4 catchup: 0 chiamate stanotte e buchi aperti saliti a 1300) + 7 reperti
minori. **Pronto per l'accensione in paper: SÌ** (motivi in §7) — già avvenuta nel frattempo.

---

## 1. Prerequisiti

| # | prerequisito | evidenza | esito |
|---|---|---|---|
| 1.1 | base di codice | `git log -1 origin/master` = `46e619b` (= HEAD del worktree) | OK |
| 1.2 | `.env` del principale (solo nomi e 0/1) | `LIVE_ORDER_MODE=LIVE` (tetto); `SAFE_SCAN_CANALE`, `OMEGA/MIKE/SAFE_CANALE_POSIZIONI`, `TENNIS_BOT_CANALE`, `SAFE_BOT/OMEGA/MIKE/TENNIS_BOT_SVEGLIA_CANALE`, `OMEGA/MIKE/SAFE_BOT_LEGGE_CANALE`, `PUNTEGGI_CANALE`, `ESITI_ORDINI_CANALE`, `HAZARD_ATLAS_SYNC`, `MOTORE_ORDINI_CANALE`, `SCALPER_CANALE` = 1; `LIVE_MARKET_TYPES` presente. **Assenti**: `TENNIS_LIVE_ORDER_MODE` (→ l'app passa `PAPER`, `desktop/main.js:250`), `LIVE_KILL_SWITCH`, `SAFE_ORDINI_VIA_CANALE`, `OMEGA_ORDINI_VIA_CANALE`, `SAFE_TENNIS_ORDINI_VIA_CANALE`, `MIKE_USE_FLUMINE_QUEUE`, `RUNNER_AUTO_FOLLOW`, `LIVE_TEMPI_ORDINE` (acceso di serie), `TENNIS/SCALPER_AUTO_MAX_PARTITE` | conforme al brief (porte ordini via canale NON accese) |
| 1.3 | app accesa da altra sessione, nessuno la chiude | pid 15624 vivo per tutta la sessione | OK |
| 1.4 | browser | NON usato (nessuna lettura del DOM: la UI è dell'altra sessione; nessun clic) | dichiarato |

## 2. Tabella dei controlli

Legenda esito: **OK** · **KO** · **NC** = NON CERTIFICATO (motivo) · **OSS** = osservazione (non KO).

### Z0 — all'avvio nessun bot opera (letto PRIMA dell'accensione, 09:02:50 UTC)

| # | controllo | evidenza | esito |
|---|---|---|---|
| Z0.a | processi del progetto (C001, C006-C009, C011-C016) | `Z0a_processi_porte_1100.txt`: 8 servizi di `desktop/main.js:288-322` vivi (runner-calcio, runner-tennis, scanner, Omega, Safe bot, Mike sotto watchdog; scalper-service e ponte tennis `--bridge-only` senza watchdog), tutti avviati 10:56:47. `tennis-odds` è breve (non vivo alle 11:00) ma ha girato: `tennis_markets` 60 righe dopo l'avvio, max `captured_at` 08:57:56 UTC | **OK** |
| Z0.5 | porte (C002, C021-C030) | 47311-47315, 47318, 47319 (lock), 47330 (UI), 47331-47338 (canali) tutte in Listen, ognuna del processo giusto; 8787/47316/47317 non in ascolto (atteso) | **OK** |
| Z0.1 | Omega/Mike/Safe `stopped`+`paper` (C102) | `Z0b_nessun_bot_opera_0902UTC.json`: omega stopped/paper, mike stopped/paper, safe stopped/paper con `strategy_modes` 6/6 paper (anche `stats.params_effective`); `stats.boot_id` = boot di oggi su tutti e tre; nessuna attività `avvio_app_bot_fermato` (atteso: non c'era niente da fermare) | **OK** |
| Z0.2 / Z0.2bis | 4 `tennis_bot_service_control` | tutti e 4 `stopped`/`paper`, `boot_id` di oggi, `stats.fermato_all_avvio_at` 08:57:01 (canale 47337). **Lo `stopping` del 24/09 (R-E2E-2) è sparito**: fix R2 `6ac2543` confermato dal vivo | **OK** |
| Z0.2 | `tennis_bot_control` righe attive | 0 | **OK** |
| Z0.3 | scalper (C145-C148) | `scalper_service_control` stopped/paper (upd 08:57:01 = guardia d'avvio); `scalper_control` righe attive 0; `stats.auto.acceso=false` | **OK** |
| Z0.4 | `betfair_live_settings` (C033) | `order_mode=paper`, `order_mode_tetto=live`, `order_mode_tetto_at` 08:57:03 (nuovo), `order_mode_boot_id` = boot di oggi, `kill_switch=false` | **OK** |
| Z0.b | nessun ordine dopo le 10:56:41 | `betfair_live_orders` 0, `tennis_live_orders` 0, `betfair_live_order_requests` 0 | **OK** |
| Z0.c1 | `betfair_live_heartbeat` (C051) | 09:03:08: `ts` 09:03:04 (età 3,7 s), `pid` 20552 = runner calcio, `mode` `LIVE+PAPER` (= tetto LIVE, serve entrambe), `watchdog_ts` 09:03:01 | **OK** (vedi reperto M1 sul `watchdog_pid`) |
| Z0.c2 | battito sui canali (C184, C191) | 47331 `battito` ogni 10,6 s (età 2-10 ms), `mode` `LIVE+PAPER`, `streaming 0`; 47332 `battito` ogni 2,1 s, `mode` `PAPER` | **OK** |
| Z0.c3 | `hello` 47331 con `modo_ordini` + `kill_switch` (C177, C185, C037) | **a runner in attesa (nessun follow) l'hello NON porta `modo_ordini`** (lettura 1, 11:05: chiavi `sport, mode, auto_follow`). Dopo che il runner è entrato in streaming (lettura 2, 11:20, 17 mercati manuali) l'hello porta `modo_ordini` = `{effettivo PAPER, tetto_ambiente LIVE, scelto_ui PAPER, motivo ok, kill_switch false, kill_switch_letto true}` | **OK dopo lo streaming / reperto M2 a runner in attesa** |
| Z0.c4 | 47332 hello | `{sport tennis, mode PAPER}`; nessun `modo_ordini` per costruzione (`live_order_worker.py:547`: solo calcio) | **OK** |

### Z1 — scanner (C012, C082-C095, C200)

| # | controllo | evidenza | esito |
|---|---|---|---|
| Z1.1 | righe fresche | 09:03:08: calcio 19 righe, età max 0,93 s; tennis 14 righe, 0,80 s; 29 righe aggiornate negli ultimi 30 s; `safe_strategy_status` età 11 s (cadenza 10-12 s) | **OK** |
| Z1.2 | età sul canale 47336 (lettura 60 s, 11:05) | `scan_calcio` 1025 messaggi, età p50 **42 ms** / p95 **82 ms** / max 136 ms; `scan_tennis` 204, p50 44 / p95 75 ms; dopo l'accensione (30 s, 11:20) p95 155 / 132 ms. `scanner_stato`: `source=stream`, 180 mercati su 1 connessione (desiderati 179), `canale.saltati=0`, `stream_mercati_senza_quote_n=0`, `rest_books_vuoti=0` | **OK** (OSS: `saltati_client=444`, un client lento sul 47336) |
| Z1.A | verifica semantica A (3 partite × 3 istanti, 2 giri) | `semantica_A.json`, `semantica_A_giro2.json`: **prezzi best back/lay uguali al libro REST** su ~95 dei 108 lati confrontati; le ~13 differenze sono di 1-2 tick con riga scan di 0,7-4,1 s (movimento del mercato entro l'età), salvo un caso da seguire (M9); stato mercato coerente (scan OPEN 4 s prima del SUSPENDED del libro, poi SUSPENDED, poi OPEN); **minuto e punteggio scan = IPS** su 9/9 (giro 2); **size: KO K1** | **prezzi/minuto/punteggio OK · size KO** |

### Z2 / Z3

| # | controllo | evidenza | esito |
|---|---|---|---|
| Z2.1 | runner calcio vivo | heartbeat età 3,7 s; `account` sul 47331 ogni ~21 s (`available 40.56`, `checked_at` fresco) anche a runner in attesa (C045 OK) | **OK** |
| Z2.2 | runner tennis vivo | `battito` 47332 ogni 2,1 s | **OK** |
| Z3.1 | «Ordini reali» | DB `order_mode=paper`; tetto `LIVE`; `modo_ordini.effettivo=PAPER` nel canale (dopo streaming) | **OK** (a video: NC, UI non letta) |

### Canali dei bot (e) — C194-C202

| canale | letto 11:05 (bot fermi) | letto 11:20 (dopo l'accensione) | esito |
|---|---|---|---|
| 47333 Mike | `mike_stato` ogni 5,7 s con `control` {status stopped, mode paper, params} (punto 6 B ok) | `running/paper`, `mike_event` | **OK** |
| 47334 Omega | **nessun `omega_stato` in 60 s** a bot fermo (pubblica solo nel ramo `running`, `omega_service.py:7651`) | `omega_stato` ogni 4,8 s con `control` e `last_cycle` | **OK a bot acceso / NC a bot fermo** (OSS M3) |
| 47335 Safe | `safe_stato` ogni 3,1 s (dichiara `cadenza_battito_s 2.0`), `params_effective`, `fonte_scan canale`; `safe_proposta` id 258 (proposta del modello, `proposed`, paper: per costruzione, `bot_service.py:12-23`, non un ordine) | `safe_stato` + `safe_attivita` | **OK** (OSS M4 cadenza) |
| 47336 scanner | vedi Z1.2 | idem | **OK** |
| 47337 tennis | `tennis_bot_stato` ×4 stopped/paper, `canale_inoltro` collegato al 47332 | `tennis_bot_posizioni`, stato running | **OK** |
| 47338 scalper | **nessun `scalper_stato` in 60 s** (pubblica solo al cambio, `scalper_service.py:372-376`); hello dichiara `cadenza_battito_s 3.0` | `scalper_sessioni` ogni 2,4 s | **OK a bot acceso / NC a bot fermo** (OSS M3) |

Il log «canale 47338» dello scalper-service **non è leggibile** (console non salvata, K2): la prova del canale è la
porta in ascolto + hello + messaggi.

### (f) Atlante (C096, C097, C099, C262, C263, C352)

| # | evidenza | esito |
|---|---|---|
| f1 | `HAZARD_ATLAS_SYNC=1`; thread `hazard-atlas-sync` vivo **dedotto dai giri** (il nome del thread non è leggibile dall'esterno; il log `[atlante-sync] acceso` è nella console persa, K2): `hazard_atlas_leghe` 9 righe v4 alle 08:57:01, **20 righe v4 in 3 giri** (ultimo 09:22:09), ogni ~10 min come `HAZARD_ATLAS_CICLO_S` 600 | **OK** |
| f2 | `Betfair/omega/data/hazard_atlas_live.json` scritto 10:59:28 (2,31 MB) e 11:22:13 (2,78 MB); `hazard_atlas_stato.json` 10:59:28, 11:12:09 | **OK** |
| f3 | `hazard_atlas` 1 riga, `generated_at` 06:19:06 UTC di oggi (prima dell'avvio: R-E2E-6 di ieri superato) | **OK** |
| f4 | `hazard_atlas_leghe.league_name` NULL su 20/20 | **OSS M5** |

### (g) TacticAI (Z8)

`fixture_predictions` di oggi: 1186 righe, **8** con `tactical_engine_json`, generate fra il 13/09 e il 23/09
(vecchie); **0 payload generati dopo `43e1468`** (25/09 14:13 UTC) → `negativi` = 0 su 0. L'unica action che li
rigenera (`today_predictions_backfill.yml`) del 25/09 è partita alle 07:56 UTC, PRIMA del fix; quella di oggi
(36227977240) è **in corso** dalle 07:50 UTC (1h33' alle 09:23). **NC**: il controllo `under_0_5 < 0` non ha ancora
dati su cui girare; va rifatto a fine action. Nota: 8/1186 con payload oggi (25/09: 34/262) — il terzo motore
copre pochissime partite (da capire a fine action, non un KO finché l'action non chiude).

### (h) Catchup e quota (Z9, C5 action)

| # | evidenza (`gh run view 36223432528 --log`, salvato in `catchup_36223432528.log`) | esito |
|---|---|---|
| h1 | ultima `seasons_catchup` 06:20 UTC **success**; REFERTO BUCHI presente (formato atteso) | OK |
| h2 | «**Chiamate fatte stanotte: 0** … Fermato per: action concorrente in_progress: `retrain_models.yml`»; «**BUCHI APERTI: 1300** lega-stagioni, ~171410 chiamate» (25/09 h19:20: 961) | **KO K4** (Z9 attende il calo) |
| h3 | quota: contatore API 649/7500 (fonte `/status`), riserva action **3000** (corretto: alle 06:21 le 3 action di oggi non erano ancora girate), margine 3851; `api_call_log` oggi 2149 righe alle 09:10 | OK |
| h4 | «[QUOTA] controprova: api_call_log conta 749 > contatore 649» | OSS M6 (due contatori divergenti di 100) |
| h5 | action di oggi: `daily_yesterday_backfill` success 06:05; `today_predictions_backfill` in corso; `predictions_results_backfill` in corso; `Daily Yesterday` del 25/09 **failure** (15 s) | informativo |

### (i) Auto-follow (C055, C187)

Prima dell'accensione: `live_follow` 0 righe `origine='auto'`; hello 47331 `auto_follow.acceso=true` ma
`feed.letto=null, partite 0, attori []`. Dopo l'accensione (11:20): ancora `mercati_auto 0`, `feed.letto null`,
`live_follow` solo 2 righe `manuale` STREAMING. Causa dal codice: il proattivo legge il feed solo se `safe` o `omega`
sono collegati a `/comando/<attore>` del 47331 (`auto_follow.py:91 ATTORI_CALCIO_DEFAULT`, `:862-876`), cioè solo
con `SAFE_ORDINI_VIA_CANALE`/`OMEGA_ORDINI_VIA_CANALE`, oggi spente. **NC** (porta via canale non accesa) + **K3**.
Tennis: 5 righe `tennis_live_follow` `origine='auto'` STREAMING dopo l'accensione (auto-mode tennis vivo, C078).

### (j) F0 — dove finisce la console

`desktop/main.js:260-267` ristampa stdout/stderr dei figli con `console.log` del processo Electron; nessun file di
log (`grep` su `main.js`: nessun `createWriteStream/appendFile`). L'exe è **portable**, lanciato senza console
(il padre 8452 non esiste più); `%APPDATA%\AlphaScore Trading` non contiene log; nessun `*.log` scritto nel repo dai
servizi dopo le 10:56 (ricerca su tutto il principale). **La console è persa** → `leggi_tempi_ordine` non ha input.
Prova dello strumento: `python -m Betfair.stream.tools.leggi_tempi_ordine console_vuota.log --per-via` → «nessuna
riga tempi_ordine trovata», exit 0: **lo strumento è pronto, il canale di misura NO**. **KO K2** (Z5 non eseguibile
con l'app avviata così).

### (l) Z13 a bot fermi

| # | evidenza | esito |
|---|---|---|
| Z13.1 | vedi Z0 | **OK** |
| Z13.2 | paper/live: tetto calcio `LIVE` (runner serve LIVE+PAPER), effettivo **PAPER** dal DB e dal canale; tennis `TENNIS_LIVE_ORDER_MODE` assente → `PAPER` (hello/battito 47332). Righe di oggi dopo l'avvio: 0 ordini (prima); dopo l'accensione (09:19 UTC) **tutte `paper`**: omega_trades 3, mike_trades 2, tennis_live_orders 1, tennis_bot_control 20 (paper, dry_run false), scalper 2 sessioni dry_run | **OK** |
| Z13.3 | calcio/tennis distinti: canali separati (47331/47336 calcio+tennis su topic separati `scan_calcio`/`scan_tennis`, 47332/47337 tennis), tabelle separate | **OK** (UI non letta) |
| Z13.x | nessun ordine possibile a bot fermi | 0 righe ordine/coda fra 08:56:41 e 09:02:50 UTC | **OK** |

## 3. Id certificati (evidenza in §2 e nei file)

C001, C002, C004, C006 (conteggio), C007, C008, C009, C011, C012, C013, C014, C015, C016 (esecuzione dedotta da
`tennis_markets`), C020 (8787 non in ascolto), C021-C030, C033, C037 (dopo lo streaming), C045, C051, C060, C076,
C077, C078 (dopo l'accensione), C082, C084, C086, C094, C096, C097, C099, C102, C116, C128, C143, C147, C148, C149,
C150 (dopo l'accensione), C157, C174, C176, C177, C184, C185 (hello), C190, C191 (battito), C194, C195, C198 (a bot
acceso), C199, C200, C201, C202 (sessioni, a bot acceso), C262, C263, C348, C349, C352, C356, C362-C364, C366,
C367, C369, C374, C381, C392, C413/C414 (assenti = default).

## 4. KO (nessuna correzione)

**K1 — le size del feed unico sono in sterline, i bot le trattano come euro (money-relevant, conservativo).**
Evidenza: su 94 confronti a prezzo uguale fra `safe_strategy_scan.payload.odds.*_size` e `listMarketBook` REST dello
stesso mercato, rapporto scan/libro mediana **0,860** (69 confronti fra 0,855 e 0,865; gli altri = size cambiate fra le
due letture). Esempi: 3,0 € → 2,58; 37,5 → 32,24; 527,39 → 453,47. Costante = cambio EUR→GBP: l'Exchange Stream dello
scanner restituisce importi in GBP, il REST nella valuta del conto (EUR). Nessuna conversione nel codice (`grep
GBP|currency` su `Betfair/safe_strategy`, `config_stream.py`: 0). Dove pesa: le size entrano nelle decisioni
(`Betfair/safe_strategy/engine.py:501-502,631-632,1223,1251,1316` `entry_size`/liquidità; proposte «64 EUR
abbinabili», `min_size 10`). Effetto: liquidità **sottostimata del 14%** (errore prudente, mai un sovra-ingresso), ma
«ciò che vede il trader» in euro è falso. Da verificare se vale anche per la ladder del runner (stesso stream API).
Riproduzione: `AUDIT_2026-09-25/e2e_fase2_z0/semantica_A.py` + `analisi_semantica_A.py`. File sospetto:
`Betfair/safe_strategy/stream.py:18-22,64`.

**K2 — la console dell'app non finisce da nessuna parte: F0 (Z5) non misurabile, nessun log dei servizi.**
`desktop/main.js:260-267` (solo `console.log`), exe portable senza console. Conseguenze: righe `tempi_ordine`,
`[atlante-domanda]`, `[runner] AUTO-FOLLOW ATTIVO`, `[scalper-svc] canale 47338`, errori dei servizi: tutti persi.
Riproduzione: avviare l'exe dal doppio clic e cercare un file con `tempi_ordine`. Serve una decisione (redirigere
stdout dell'exe in un file o un file di log in `main.js`): è un cambio di codice/processo, **non fatto**.

**K3 — l'auto-follow calcio «proattivo» non segue nessuna partita nella configurazione attuale.**
`Betfair/stream/auto_follow.py:91` (`ATTORI_CALCIO_DEFAULT = ("safe","omega")`), `:862-876`: senza un attore collegato a
`/comando/` il feed non si legge e le candidate si liberano. Con `SAFE/OMEGA_ORDINI_VIA_CANALE` spenti (decisione D-1
aperta) il log «AUTO-FOLLOW ATTIVO: i bot operano da soli su tutte le partite» (runner.py:1907) promette ciò che non
accade. Evidenza: hello 47331 alle 11:05 e alle 11:20 (`attori []`, `feed.letto null`, `mercati_auto 0`). Non un bug
del codice rispetto al suo progetto, ma il controllo (i) del brief e i 7.2.x del piano non possono passare così.

**K4 — catchup: 0 chiamate stanotte, buchi aperti 961 → 1300.** Fermato da `retrain_models.yml` in corso (esclusività
R5, voluta), ma la regola dell'utente «DB sempre aggiornato senza buchi» non è rispettata stanotte; la crescita
viene anche dalle 1413 stagioni passate verificate. Evidenza: `catchup_36223432528.log` righe 3172-3186.

## 5. Reperti minori (OSS)

- **M1** `betfair_live_heartbeat` ha UNA riga (id=1): i 6 watchdog scrivono tutti `watchdog_ts/watchdog_pid` sulla
  stessa riga (`watchdog.py:113-117`, `db.py:840-849`); alle 09:03 `watchdog_pid=33164` è quello di **Omega**, non del
  runner. Se il watchdog del runner morisse, gli altri 5 lo nasconderebbero.
- **M2** a runner calcio in attesa (nessun follow) l'hello 47331 non porta `modo_ordini`/`kill_switch`: il worker che
  lo pubblica vive solo dentro `framework.run()` (`live_order_worker.py:3610`, ramo di attesa `runner.py:1986-2039`
  senza `_refresh_settings`). La UI ripiega sul DB (corretto, ma non «dal canale»).
- **M3** Omega (47334) e scalper (47338) non pubblicano lo stato a bot fermo (scalper solo al cambio, pur dichiarando
  `cadenza_battito_s 3.0`): chi si collega a bot fermo non riceve niente fino al primo cambio.
- **M4** Safe `safe_stato` ogni 3,1 s (max 3,6) contro `cadenza_battito_s 2.0` dichiarata (a bot fermo).
- **M5** `hazard_atlas_leghe.league_name` sempre NULL.
- **M6** quota API: `api_call_log` 749 contro contatore `/status` 649 (log del catchup).
- **M7** all'avvio il runner scrive in `live_alerts` un **CRITICAL** «Live trading: modalita' LIVE attiva. *** LIVE ***
  ORDINI REALI (SOLDI VERI) attivi» (id 493, 08:57:03 UTC) mentre l'effettivo è PAPER: `runner.py:1608-1629` annuncia
  il TETTO, non il modo effettivo. Allarme fuorviante.
- **M9** FC Ryukyu v Ehime (36115980), lay «away»: scan **3,10** (size 6,88 = 8 € in GBP) contro libro **2,94** (11:16:06)
  e **3,05** (11:16:27), con riga scan di 0,7-1,8 s: a due istanti distanti 20 s lo scanner mostra un lay peggiore del
  libro, con la stessa size. Possibile livello migliore mancato dallo stream a 1 livello (o livello sotto il minimo);
  campione troppo piccolo per dirlo difetto: da osservare nei prossimi confronti.
- **M8 (sicurezza)** il token dei comandi dei canali è in chiaro nella riga di comando del renderer
  (`--alphascore-canale-token=…`, `desktop/main.js:63-70`), leggibile da ogni processo locale dell'utente.

## 6. NON CERTIFICATO (motivo)

- Porte ordini via canale Safe/Omega/Safe tennis (C113, C142, C189 lato bot, C378): **porta via canale non accesa**.
- Auto-follow proattivo calcio (C055 ramo feed, 7.2.1-7.2.11): **porta via canale non accesa** (K3). Il log
  «AUTO-FOLLOW ATTIVO» e «motore ordini ATTIVO» (C056): console persa (K2).
- F0/Z5 tempi degli ordini (C058): console persa (K2).
- TacticAI Z8: **action del giorno in corso** (0 payload dopo `43e1468`).
- Stato Omega/scalper sul canale a bot fermo (C198/C202 a riposo): non pubblicato per costruzione (M3).
- `avvio_app_bot_fermato` (C102 ramo «c'era da fermare»): non esercitato (nessun bot acceso ieri sera).
- Tutto ciò che è a video (chip `cr-*`, U-xxxx): **UI non letta** (nessun browser usato in questa sessione).
- Scalper/tennis/Omega/Mike/Safe durante il lavoro (Z4, Z6, Z7, Z11-Z14): **bot spenti** al momento della lettura; è la
  fase successiva (i bot sono stati accesi alle 11:10-11:18).
- Log di vita dei worker (C031, C059, C080, C081, C094, C096, C145, C157…): console persa (K2); certificati solo dagli
  effetti (porte, messaggi, righe DB).
- `/status` API-Football non chiamato (riserva ricalcolata solo dal log e da `api_call_log`).

## 7. Pronto per l'accensione dei bot in paper?

**SÌ.** Nessun bot operava all'avvio (tutti `stopped/paper`, 0 righe attive, 0 ordini), `order_mode=paper`,
`kill_switch=false`, tennis a `PAPER` di tetto, feed fresco e fedele al libro nei prezzi, minuto e punteggio. I KO
trovati non rendono il paper pericoloso: K1 è prudente (sottostima la liquidità), K2/K3 tolgono misure e una funzione
non richiesta dalla configurazione attuale, K4 riguarda i dati storici. Da dire all'utente prima di leggere i
risultati del paper: (1) il paper NON è ri-certificato sul banco per i cambi del 25/09 (§0.5 del piano); (2) nessuna
misura dei tempi (K2); (3) le size mostrate e usate sono in sterline (K1); (4) l'auto-follow calcio non lavora (K3).

## 8. File creati e comandi eseguiti (tutti in sola lettura)

File (in `AUDIT_2026-09-25/`): `E2E_FASE2_Z0_AVVIO_2026-09-26.md` (questo); `e2e_fase2_z0/`: `Z0a_processi_porte_1100.txt`,
`Z0b_nessun_bot_opera_0902UTC.json`, `Z0_letture_sql_varie.json`, `canali_lettura_1.json` (60 s, 11:05),
`canali_lettura_2_dopo_accensione.json` (30 s, 11:20), `semantica_A.json`, `semantica_A_giro2.json`,
`catchup_36223432528.log`, `console_vuota.log` (vuoto, input della prova F0); strumenti: `lettore_canali.py`,
`semantica_A.py`, `analisi_semantica_A.py`, `analisi_canali.py`, `estrai_inventario.py`.

Comandi:
- `git fetch`, `git log` (base 46e619b): OK.
- `Get-CimInstance Win32_Process`, `Get-NetTCPConnection -State Listen`: OK.
- ~16 SELECT via MCP `execute_sql` (progetto `dqbwaocvlzbxfrpacsac`): control, settings, ordini, code, heartbeat, scan,
  atlante, `fixture_predictions`, `api_call_log`, follow, `live_alerts`, `tennis_markets`, `information_schema`: OK
  (2 errori di sintassi miei, corretti; nessuna scrittura).
- `lettore_canali.py` 2 volte: WebSocket `/lettore/<topic>` sulle porte 47331-47338, **nessun messaggio inviato**, mai
  `/comando/`, nessun token: OK.
- `semantica_A.py` 2 volte (il primo giro aveva un errore mio sui nomi dei campi del punteggio): **Betfair** per giro
  1 login (sessione propria), 3 `listMarketBook` (EX_BEST_OFFERS), 3 `get_scores` IPS, 1 logout della propria sessione
  → in totale 2 login, 6 listMarketBook, 6 get_scores, 2 logout; Supabase: sole SELECT su `safe_strategy_scan`. OK.
- `gh run list` (4 workflow), `gh run view 36223432528 --log`: OK.
- `python -m Betfair.stream.tools.leggi_tempi_ordine console_vuota.log --per-via`: exit 0, «nessuna riga».
- Ricerca file `*.log/*.jsonl/*.txt` scritti dopo le 10:56 nel principale (sola lettura).
- Nessun processo dell'app avviato/fermato, nessuna scrittura DB, nessun clic, nessun commit.
