# E2E REALE — FASE 1 (APP SPENTA, BOT FERMI) — ESITI — 25/09/2026

Delegato Opus del coordinatore (sessione B), worktree `agent-ae6b4a3f84a6ad933`, base `origin/master` = `5798754`
(verificato con `git fetch`: nessun commit più recente). Nessun commit. Piano: `PIANO_TEST_E2E_REALE_2026-09-25.md`
§1, §2 (P01-P32), §5.1. Inventari: `INVENTARIO_COMPONENTI_2026-09-25.md`, `INVENTARIO_CAMPI_UI_2026-09-25.md`.
Evidenze (una per passo): `AUDIT_2026-09-25/e2e_fase1/` (113 file). Strumenti: `AUDIT_2026-09-25/e2e_fase1/strumenti/`.

**Esito sintetico: P01-P31 tutti OK (13 file di esito + C295), 0 KO del codice. P32: DB tornato byte per byte alla
fotografia, al netto della migrazione `uscite_manuali_default_2026-09-25.sql` applicata dall'utente alle 18:45:22 UTC
DURANTE il test (dopo l'ultimo ripristino dei percorsi, 18:41:53): 0 differenze nette. 12 reperti da portare all'utente
(nessuno blocca la fase 2; R-E2E-1, -2, -6 vanno saputi PRIMA).**

---

## 0. COME è stata eseguita l'azione «dalla UI» (dichiarazione obbligatoria)

- **Browser automation NON disponibile**: `vite preview` ha servito `frontend/dist` (HTTP 200 su `/` e sul bundle
  `assets/js/index-7JcMHgku.js`), ma l'estensione Chrome rifiuta `http://127.0.0.1:4173` e `http://localhost:4173`
  («This site is blocked by your site permissions»). In ogni caso il delegato non ha le credenziali del proprietario:
  le RPC sono owner-only e il login non era possibile.
- **Ripiego usato (più forte della sola funzione TS)**: i COMPONENTI VERI della Control Room montati in jsdom
  (vitest) — `PannelloBot`, `RigaOrdiniReali`, `RigaFreno`, `ProtectedRoute` — con i COMANDI VERI costruiti come in
  `pages/ControlRoom.tsx:264-304` (`creaComandiControlRoom`, `components/controlroom/comandiBot.ts:100`, con la
  rilettura fresca di Safe dal DB), le righe costruite da `righeInterruttori` (`righeBot.ts:62`), gli importi da
  `importiInterruttori` e le uscite da `usciteInterruttori`/`conPosizioniAperte` (`lib/interruttori.ts`), lo stato
  letto con le fetch vere della UI (`fetchOmegaState`, `fetchSafeState`, `fetchMikeState`, `fetchTennisBotServices`,
  `fetchScalperControlRoom`, `statoBotScalper`, `leggiVarianti`/`leggiModiStrategia` di `useControlRoom.ts:3619,3713`).
  I clic sono sui `data-testid` del piano (`fireEvent.click`), con l'attesa anti-doppio-clic vera (400 ms).
- **Client Supabase**: `@/integrations/supabase/client` sostituito da un client VERO con la SERVICE ROLE del `.env`
  radice (`frontend/e2e_fase1/clientVero.ts`). `betfair_live_is_owner()`/`tennis_is_owner()` accettano il service
  role (`migrations/betfair_live_order_queue.sql:176-190`, `tennis_orders.sql:30-40`). Guardie: solo le RPC del piano +
  `get_*`; nessuna scrittura diretta su tabella; realtime stub; ogni RPC registrata con gli argomenti
  (`Pxx_esito.json` → `rpc`). Esito delle guardie: **0 RPC fuori piano, 0 scritture dirette** in tutti i percorsi.
  Differenza dichiarata: `betfair_live_settings.order_mode_updated_by` = `"service_role"` (con il login vero sarebbe
  l'email del proprietario: NON verificato, fase 2).
- **Dove il componente non è montabile ad app spenta** si è chiamata la STESSA funzione TS della UI (dichiarato nel
  percorso): P06 (funzioni della pagina Omega `lib/omega.ts:1216 omegaParamsPatch`, `:1243 activateOmega`), P20
  (`lib/tennis.ts:949 setTennisBotUscite`: `UsciteTennis` compare solo con `stats.auto` scritto dal ponte acceso),
  P21 (`lib/tennis.ts:856 armTennisBot`, `:875 disarmTennisBot`, come `TennisBotPanel.tsx:532-551`), P22 caso negativo
  (`lib/scalperControlRoom.ts:165 attivaScalperAuto`: la UI non offre il live a caldo), P24 (`lib/scalper.ts:141
  activateScalper`, come `ScalperPanel.tsx:174`), P28-P31 (`safeBot.ts:1284`, `controlRoomProposte.ts:374`,
  `omegaProposte.ts:320`, `safeBot.ts:1142`, `mike.ts:1958`, `tennis.ts:465`).
- **Sveglie** (`svegliaBot`): registrate e non inviate (canali spenti; best-effort per costruzione,
  `localChannel.ts:338-344`). Conteggio nei `Pxx_esito.json`.
- **Sonda dei servizi** (`strumenti/sonda.py`, piano §1.7): chiama in sola lettura, col `.env` vero,
  `omega_db.read_control` + `omega_config.resolve_params` + `omega_proposte.modo_uscite`; `mike.db.read_control` +
  `mike.config.merge_params`; `safe_strategy.bot_db.read_control` + `bot_service.resolve_params` /
  `modalita_di_strategia` / `uscite_automatiche_di`; `tennis_db.list_tennis_bot_services` +
  `tennis_bot_service.stato_desiderato`; `scalper_service.Db().servizio()`; `trading.controls.get_live_settings(force)`
  + `motivo_kill_switch` + `modo_ordini.descrivi(LIVE_ORDER_MODE, order_mode)`. **Verificato: 1 thread prima
  dell'import, 1 dopo, 1 alla fine** (nessun thread, nessun `run_once`, nessun `set_*`, nessun `log`).
- **Fotografie**: `strumenti/e2e.py foto` (GET PostgREST, sola lettura) salva le righe intere E il TESTO GREZZO di
  ogni riga di controllo (`Accept: application/vnd.pgrst.object+json`): il confronto è sui valori E byte per byte.
- **Ripristino esatto**: gesto UI del piano (ferma / passa a prova / valore di prima) e poi PATCH della riga col suo
  testo grezzo della fotografia PRIMA (`e2e.py ripristina`); cancellate SOLO le righe create dal test
  (`omega_daily_goal` del 25/09 creata da `omega_snapshot_daily_goal`; `tennis_bot_control` (36063889, tennis_flb) di P21).
  Nessun trigger sulle tabelle toccate (verificato su `information_schema.triggers`): `updated_at` torna identico.

---

## 1. Prerequisiti verificati (non presunti)

| # | prerequisito | evidenza | esito |
|---|---|---|---|
| 1.1 | processi del progetto | `Get-CimInstance Win32_Process` alle 19:59: nessun Electron, nessun python del repo; attivi solo `npm run build` del coordinatore (`vite build` PID 25956, in `frontend/` principale), finito prima dell'inizio. Alle 20:53: 0 processi del repo | OK |
| 1.2 | porte 47311-47338 e 4173 | `Get-NetTCPConnection -State Listen` vuoto all'inizio e alla fine | OK |
| 1.3 | `frontend/dist` | `dist/index.html` 19:59:58 > ultimo commit di `frontend/src` 19:58:04 (`5798754`); `frontend/src` del principale = quello del worktree (`diff -rq --strip-trailing-cr`: identici); il bundle unico contiene tutti i `data-testid` e le RPC del piano (35 stringhe cercate, 34 trovate; `cr-modalita-all-avvio-scalper` è un template `cr-modalita-all-avvio-${id}`) | OK (build NON rilanciata da me) |
| 1.4 | migrazioni (firma delle RPC, sola lettura) | 34 RPC del piano presenti con UNA sola firma ciascuna (`pg_proc`); `safe_request` con `v_atteso`; `mike_request` con `approva_uscita`; `safe_stop` scrive `mode='paper'`; `tennis.backMin`=1.02; `base` 20-34; colonne `uscite_automatiche`/`origine`; `scalper_service_control`; `omega_request_approve(bigint,numeric,jsonb)`; `omega_transitions_status()`; `get_direction_eta`; `get_market_delays` con `n_ht_missing` (market_delays_ht applicata); `get_live_follows` con `origine` + `idx_lf_origine_auto` | OK: tutte le migrazioni di §1.1 risultano applicate |
| 1.5 | fotografia iniziale | `e2e_fase1/fotografia_iniziale.json` (18:10:52 UTC) + `controllo_stabilita.json` (0 differenze a distanza) | fatta |
| 1.6 | stato dei bot | omega/mike/safe `stopped/paper`; scalper servizio `stopped/paper`; `order_mode=paper`, tetto `live`, `kill_switch=false`; righe per partita attive 0/0 | OK |
| 1.7 | **4 `tennis_bot_service_control` in `stopping`** dal 24/09 16:06 | fotografia | **NON conforme a §1.4 (atteso `stopped`)** → R-E2E-2 |
| 1.8 | code aperte | `omega_manual_requests` id 49 `proposed` (cashout paper, 24/09 15:09); `safe_strategy_requests` id 257 `proposed` (place modello paper, 24/09 16:03); altre code 0 | preesistenti, NON toccate → R-E2E-5 |
| 1.9 | `.env` (solo nomi e 0/1) | `LIVE_ORDER_MODE=LIVE`; `SAFE_SCAN_CANALE`, `*_CANALE_POSIZIONI`, `*_LEGGE_CANALE`, `*_SVEGLIA_CANALE`, `PUNTEGGI_CANALE`, `ESITI_ORDINI_CANALE`, `HAZARD_ATLAS_SYNC`, `MOTORE_ORDINI_CANALE`, `SCALPER_CANALE`, `SAFE_BOT_GIRO_VELOCE`, `MIKE_LIVE_ENABLED` = 1; `LIVE_MARKET_TYPES` presente (13 tipi); `LIVE_KILL_SWITCH`, `SAFE/OMEGA/SAFE_TENNIS_ORDINI_VIA_CANALE`, `MIKE_USE_FLUMINE_QUEUE` assenti | **`MOTORE_ORDINI_CANALE=1` e `SCALPER_CANALE=1` sono nel `.env`**: la tabella §1.2 del piano li dà «assente» / «di serie spento» → da riallineare |

---

## 2. Tabella P01-P32

Colonne: esito · righe prima/dopo (file) · ripristino (valori/grezzo vs PRIMA e vs base) · id certificati · note.
«base» = `fotografia_iniziale` (percorsi prima delle 18:45) o `fotografia_post_migrazione` (riesecuzioni dopo).

| P | esito | prima → dopo | ripristino | id C/U certificati (fase 1) | note (numeri) |
|---|---|---|---|---|---|
| P01 | **OK** | `P01_prima` → `P01_dopo` | 0/0 · 0/0 | C298, C205, C213(lato), U0205, U0206, U0219; C103 sonda | `omega_activate(p_mode=paper, p_daily_goal=100, p_params` = params INTERI) → running/paper, params identici (0 chiavi diverse), error/stopped_at NULL; sonda `running paper`; effetto laterale: riga `omega_daily_goal` 2026-09-25 goal 100 (cancellata al ripristino) |
| P02 | **OK** | `P02_prima` → `P02_dopo_live` → `P02_dopo_paper` | idem | C298, U0217 | 1 clic su `cr-a-live-omega`: conferma compare DISABILITATA; dopo 1,5 s `mode`/`updated_at` invariati; conferma → `omega_update_params(p_mode=live)` senza params/goal → live, running, params identici; sonda `running live`; `cr-a-paper-omega` → paper |
| P03 | **OK** | → `P03_dopo` | idem | C298, U0216 | `omega_stop` → `stopping`, mode invariato; sonda `stopping`; a video «sta fermandosi», nessun «avvia»; title «ferma le APERTURE…» |
| P04 | **OK** | `P04_prima` → `P04_dopo` | 0/0 · 0/0 | U0215 | 0,5 → 0,6: SOLO `min_stake` cambia; sonda `resolve_params.min_stake=0.6`; ritorno dal campo a 0,5 |
| P05 | **OK** | → `P05_dopo_automatiche`, `P05_dopo_manuali` | 0/0 · 0/0 | C300, U0214; C106 sonda | a video «manuali» = DB; 1° clic non scrive (conferma verso automatiche, dal 25/09 sera); conferma → `uscite_protezione='automatico'` e nient'altro; sonda `modo_uscite=automatico`; «passa a manuali» → `avvisa_e_proponi` (vedi R-E2E-11: la chiave, assente in foto, diventa esplicita) |
| P06 | **OK** | `P06_prima` | 0/0 · 0/0 | C320 (solo funzioni) | `omegaParamsPatch(server, {...OMEGA_PARAM_DEFAULTS, ...server})` = server (0 chiavi tolte/aggiunte); stessa riga di P01 (running/paper, params identici); `stopOmega` → stopping |
| P07 | **OK** | `P07_prima` → `P07_dopo_paper`, `P07_dopo_live` | 0/0 · 0/0 (2 giri) | C298, C217, U0219; C120 sonda | `mike_activate(p_mode=paper)` SENZA p_params → params identici; avvio soldi veri: conferma disabilitata, 1 clic non scrive, conferma → running/live, params identici |
| P08 | **OK** | → `P08_dopo_live` | idem | U0217 | `mike_update_params(p_params` = letti INTERI, `p_mode=live)`; sonda `running live`; ritorno paper |
| P09 | **OK** | → `P09_dopo` | idem | U0216 | `mike_stop` → stopping/paper |
| P10 | **OK** | → `P10_dopo` | idem | C300, U0214; C123 sonda | a video «manuali» = `merge_params`=false; conferma → `uscite_automatiche=true` e nient'altro; sonda true; ritorno false. Rieseguito dopo la migrazione: OK |
| P11 | **OK** | `P11_prima` → `P11_dopo` | 0/0 · 0/0 (2 giri) | C298, C222, U0205, U0219; C130 sonda | `safe_activate('paper', params INTERI)`: running/paper, `variants=["base"]`, `strategy_modes` 6/6 `paper`; cambia solo `variants`; sonda identica |
| P12 | **OK** | → `P12_dopo` | idem | C298 | clic su «Safe esatto» sulla STESSA plancia (istantanea vecchia) → rilettura fresca → `safe_update_params`, `variants=[base,esatto]`, `started_at` invariato (reperto A chiuso) |
| P13 | **OK** | → `P13_dopo_live` | idem | U0217 | punta accesa poi soldi veri: tetto live, punta live, base/esatto paper, tennis/model/manual invariati, running; sonda punta live/base paper; ritorno: punta paper, tetto paper |
| P14 | **OK** | → `P14_dopo` | idem | U0216 | spente esatto e punta (`safe_update_params`), poi base → `safe_stop`: stopping, `mode=paper`, `variants=["base"]` (mai `[]`) |
| P15 | **OK** | `P15_prima` → `P15_dopo`, `P15_dopo_live` | 0/0 · 0/0 | C307, C318, U0195(filtro) | scheda tennis senza righe calcio; `variants=["tennis"]`, 6 modalità paper (model/manual portati a paper), stake tennis 3 (già 3: cambia solo `variants`); live: tetto+tennis live, altre paper; «passa a prova» cambia SOLO `strategy_modes` |
| P16 | **OK** | → `P16_dopo_model_live`, `P16m_dopo_live` | 0/0 · 0/0 | C298, U0217, U0219 | (a) fermo: clic su `cr-avvia-paper-safe-model` → `SafeFermoPerStrumento`, 0 scritture; (b) model live: tetto live, base/esatto paper; sonda model live/base paper/manual paper; (c) ritorno. P16m «a mano»: nessun blocco uscite; «ferma» → `StrumentoSenzaSpegnimento`, 0 scritture; manual live → tetto live, sonda manual live; ritorno |
| P17 | **OK** | → `P17_dopo` | idem | C300, U0214; C136 sonda | base: a video = `uscite_automatiche_di` (manuali); conferma → `uscite_automatiche.base=true`, cambia solo `uscite_automatiche`; sonda true |
| P18 | **OK** | → `P18_dopo` | idem | U0215 | `stake.per_strategia.base` 2 → 2,5: dentro `stake` cambia SOLO `per_strategia.base`; sonda 2.5 |
| P19 | **OK** | `P19_prima` → `P19_dopo_avvio`, `P19_dopo_ferma` | 0/0 · 0/0 (2 giri) | C298, C248, U0205, U0206, U0215, U0216, U0217, U0219; C078 sonda | riga `stopping` dal 24/09: a video «sta fermandosi», NESSUN avvia (R-E2E-2); preparazione `stopping→stopped` (come `ripresa_ponte`); avvio → running/paper, stake/params conservati, altri 3 invariati; live: `tennis_bot_service_update_params(p_mode=live, stake/params null)`; stake 2→2,5 solo colonna; ferma → stopping, `stopped_at` valorizzato |
| P20 | **OK (funzione TS)** | — | idem | C248 (colonna), C079 sonda | `tennis_bot_service_set_uscite`: solo `uscite_automatiche` (prima true→false, dopo la migrazione false→true), status/mode/stake/params invariati; sonda `stato_desiderato.uscite_automatiche` coerente. Componente `UsciteTennis` NON certificato (R-E2E-10) |
| P21 | **OK (funzione TS)** | → `P21_dopo` | idem (riga cancellata) | C249 | arma dry_run=true → requested/paper/true; riarmo su riga attiva rifiutato («bot già attivo o in chiusura»); disarmo → stopping; con dry-run TOLTO la riga nasce comunque `mode='paper'`, `dry_run=false` (R1 del piano confermato) |
| P22 | **OK** | `P22_prima` → `P22_dopo_avvio`, `P22_dopo_ferma` | 0/0 · 0/0 (2 giri) | C298, C258, C331, U0215, U0216, U0218, U0219; C149 sonda | `scalper_auto_activate(paper)`: running/paper, stake/strategia/params conservati; a video nota «modalità solo all'avvio», nessun «passa a soldi veri»; live a caldo → «scalper gia' acceso in paper…», 0 scritture; stake 25→30 solo colonna; ferma → `stopped`, `scalper_auto_stop` ok |
| P23 | **OK** | → `P23_dopo` | idem | C300, C258, U0214; C165 sonda | a video «manuali — 0 posizioni aperte»; conferma → `scalper_uscite_automatiche(true)` ok; `params.uscite_automatiche=true`; sonda true |
| P24 | **OK (funzione TS)** | — | idem | C259 (negativo) | `scalper_activate('E2E_NON_SEGUITO_25092026','maker',true,25)` → «evento non seguito… (segui prima la partita)»; `scalper_control` 25 → 25 righe |
| P25 | **OK** | `P25_prima` → `P25_accesi` → `P25_dopo` | 0/0 · 0/0 | C299, U0196, U0197 | 5 servizi accesi in prova dalla UI; `cr-ferma-tutti` (nessuna conferma) → Omega/Mike/Safe stopping (Safe `mode=paper`), tennis_flb stopping, scalper stopped; nessun «non fermati» |
| P26 | **OK** | `P26_prima` → `P26_dopo_live` | 0/0 · 0/0 | C302, C229, U0199, U0202, U0203; C036/modo_ordini sonda | a video prima della lettura «OFF - nessun ordine» + «modo ordini non letto…», dopo la lettura «PAPER - prova», tetto LIVE, fonte db; OFF: `order_mode=off`, kill invariato, sonda effettivo OFF; PAPER; LIVE: conferma disabilitata, 1 clic non scrive, conferma → live, a video LIVE, sonda effettivo LIVE (tetto .env LIVE); finale PAPER |
| P27 | **OK** | → `P27_dopo_on` | idem | RigaFreno (nuovo, non in inventario), C229; sonda | Control Room: «tira il freno» senza conferma → `kill_switch=true`, `order_mode` invariato, sonda `db_kill_switch_attivo`; rilascio: dopo 2 clic su 3 ancora tirato, al 3° false; sonda None. `LiveControlsPanel` di Segui Live NON montato (vedi §4) |
| P28 | **OK** | `P28_prima` → `P28_dopo` | 0/0 · 0/0 | C225 (negativo) | id inesistente → «richiesta 999999999 inesistente»; id 256 chiuso → `ok:false` → «la proposta non è più in attesa di approvazione» (anche con prezzo/contesto); `safe_request('kind_inventato')` → «kind non valido» |
| P29 | **OK** | idem | idem | C210 (negativo) | inesistente → eccezione; id 48 non proposed → «la proposta non e' piu' in attesa…» |
| P30 | **OK** | idem | idem | C221 (negativo) | `approva_uscita` senza chiave → «approva_uscita senza chiave della proposta»; `cashout {}` → «payload senza event_id» |
| P31 | **OK** | idem | idem | C255 (negativo) | bot inventato → «bot non valido per chiudi_bot»; event_id vuoto → «event_id obbligatorio per chiudi_bot». P28-P31: `confronta(P28_prima, P28_dopo)` = 0/0 (max id delle 5 code invariati: 257/49/3/18/99; righe 256/48/257/49 intatte) |
| P32 | **OK (al netto della migrazione esterna)** | `fotografia_iniziale` → `P32_finale` | vedi §6 | C205 C213 C217 C222 C229 C248 C249 C258 C259 + code | `P32_finale` vs `fotografia_post_migrazione`: **0 valori, 0 byte**; vs `fotografia_iniziale` con la migrazione applicata a mano (`strumenti/p32_netto.py`): **0 differenze** |

**Falsificazione.** (1) Mutazione temporanea `PannelloBot.tsx:478 ATTESA_CONFERMA_MS = 0` → P01-P03 diventa **KO**
su «conferma INERTE subito» (`FALSIFICAZIONE_P01_P03_esito.json`), ripristino DB comunque 0/0; mutazione tolta, `git
status` pulito, P01-P03 rieseguito OK. Una seconda mutazione (forzare `mode:'paper'` in
`cambiaModalitaServizio` di Omega) è stata **negata dal classificatore dei permessi**: non eseguita né aggirata.
(2) Il comparatore sa diventare rosso: `fotografia_iniziale` vs `P01_dopo` = 11 valori, 1 riga grezza diversa
(`falsificazione_confronto.json`). (3) Un percorso interrotto da eccezione ripristina comunque (P11 al primo giro,
«pulsante assente»: ripristino 0/0, poi corretto il banco — non il prodotto — e rieseguito).

---

## 3. Componenti/campi SCOPERTI esercitati ad app spenta

| id | controllo | evidenza | esito |
|---|---|---|---|
| C295 | `/control-room` senza sessione, `ProtectedRoute` + `useAuth` veri (MemoryRouter) | → landing, Control Room non mostrata; `isOwnerEmail` owner sì / altro no | OK (`C295_esito.json`) |
| C295/C275 | chiave ANON di `frontend/.env` | `get_safe_state`, `get_live_settings`: «permission denied for function»; `select omega_control`: «permission denied for table» | OK |
| C275 | `sicurezza_bk.verifica_b1()` (STABLE, sola lettura) | 95 controlli, 95 OK, 0 KO; tabelle `public` senza RLS: 0; funzioni eseguibili da anon: 1 (`get_market_delays`, voluta) | OK |
| C274 | publication `supabase_realtime` vs abbonamenti UI | 38 tabelle pubblicate; tutte le 31 tabelle a cui la UI si abbona (grep `table:` + `MIKE_REALTIME_TABLES` + tennis) sono pubblicate | OK |
| C215/C276 | job notturno transizioni | `cron.job` `omega_transitions_nightly` `0 4 * * *` attivo; ultimo giro `omega_transitions_runs` id 13 `ok` (13:55); `cron.job_run_details` del job: nessun giro ancora (creato il 25/09) | OK (giro notturno: fase 2/domani) |
| C216/C277 | `omega_minute_build` NON deve esistere | assente | OK |
| C211 | `omega_requests` | **la tabella NON esiste** sul DB e nessun codice la nomina (grep `.ts/.tsx/.py` = 0) | correzione inventario (R-E2E-8) |
| C212 | `omega_missions` | 23 `closed`, nessuna `running` | OK |
| C230 | `betfair_live_audit` dopo P26/P27 | ultimo id 96 (10/07) prima e dopo: **nessuna riga per i cambi di modo ordini / freno** | KO rispetto alla proposta (R-E2E-3) |
| C237 | `betfair_live_risk_state` | riga del 24/09, `mode=live`, `stop_fired=false`, `limit_off` | informativo |
| C239 | `betfair_live_risk_rules` | done 6, error 1, cancelled 7: nessuna attiva | OK |
| C254 | `tennis_markets` | 741 righe, `captured_at` max 24/09 15:52 UTC | informativo (vecchio di ~27 h: fase 2) |
| C261 | `theta_confirm_requests` | 0 in attesa | OK |
| C262/C263 | atlante hazard | `hazard_atlas_leghe` 0 righe; **`hazard_atlas` 0 righe** (max `generated_at` NULL) | R-E2E-6 |
| C264 | code pre-match vecchie | `betfair_order_requests` 0 aperte; **`betfair_refresh_requests` id 7 `pending` dal 01/09** | R-E2E-9 |
| C313 | banda della strategia | `npx vitest run src/lib/valutaProposta.banda.test.ts` (config normale, Supabase finto): 20/20 | OK |
| C439 | test di contratto registro/banco | `pytest test_registro_bot_2026_09_16.py test_contratto_strada_unica_2026_09_25.py` con `SUPABASE_URL/KEY` finte: 43 passed | OK |
| inventario avv. 1 | default uscite Mike | inventario: `config.py:252` DEFAULT True; oggi sonda `merge_params` = false e UI `usciteMikeDi` = false (coerenti) | inventario superato |
| — | `cron.job` non inventariato | **`make-daily-post-job` `00 09 * * *`**, `net.http_post` a una Edge Function `make-daily-pos…`, giri quotidiani `succeeded` | R-E2E-7 |

---

## 4. NON CERTIFICATO in fase 1 (motivo e rinvio)

- **La UI servita da `vite preview` nel browser**: estensione Chrome bloccata su 127.0.0.1/localhost:4173 e nessuna
  credenziale del proprietario → login Supabase da `localhost:4173` (piano §8.1) NON verificato; `order_mode_updated_by`
  con l'email del proprietario NON verificato. Rinvio: fase 2 (app accesa, l'utente loggato).
- **U0198** (nota «Avviando da qui parte solo…» della scheda tennis): la prop `nota` non è stata montata. Fase 2/3.
- **U0207** (età del canale), **U0221** (card d'errore della pagina), fonte «canale» di tutte le righe: servono i
  canali accesi / la pagina intera. Fase 2.
- **U0220 / C301 `UsciteTennis`**: compare solo con `stats.auto` scritto dal ponte (`tennisAuto.ts:48-68`). Fase 2.
- **U0282 / U0310 / U0341 / C303** kill-switch di Segui Live (`LiveControlsPanel`, tasto Esc): non montato (pagina
  con poll 4 s, `window.confirm`). Il freno è stato certificato dalla riga `RigaFreno` della Control Room. Fase 3.
- **TennisBotPanel (C336) come componente**, checkbox dry-run e `window.confirm` di `handleArm`: solo la funzione. Fase 3.
- **P16 barriera SQL di `safe_request` per `manual` (`v_atteso`)**: verificata solo l'esistenza nella firma viva;
  provarla richiede una riga di richiesta nuova (vietato in fase 1). Fase 2 (Z4.S7).
- **Tutti i «Servizio (fase 2)»** del piano (stopping→stopped dal servizio, giri, ordini paper, esiti, tempi): i
  servizi sono spenti per mandato; la sonda prova solo la RILETTURA.
- **C103/C120/C130/C076-C079/C149/C165** come worker: certificate SOLO le funzioni di lettura del giro (sonda).
- **Pagine dedicate intere** (Omega C320, Mike C322, Safe C324), campi U0404-U0514: fase 3 (confronto campo per campo).
- **SCOPERTI di processi/porte/canali/action (C001-C204, C278-C294)**, ENV di taratura (C348-C434), calcolo/ML
  (C442-C482): richiedono app accesa o sono di fase 3; non toccati.
- **Seconda mutazione di falsificazione**: negata dai permessi (vedi §2).

---

## 5. KO e REPERTI (nessuna correzione fatta)

Nessun KO del codice sui percorsi P01-P31. Reperti:

- **R-E2E-1 (UI↔DB, da sapere prima della fase 2) — la plancia di Safe mostra gli EFFETTIVI del servizio, non la
  riga scritta.** `useControlRoom.ts:2199-2203` legge varianti e modi da `stats.params_effective` (poi da `params`)
  (`leggiVarianti` `:3713-3725`, `leggiModiStrategia` `:3619-3635`). Ad app spenta gli effettivi sono del 24/09 16:06
  (`variants` 4/4): dopo aver scritto `variants=[base,esatto]` la riga «Safe punta» appare «in esecuzione»
  (asserzione OSS-EFF, `P11_P18_esito.json`). I COMANDI non ne soffrono (rilettura fresca dal DB, P12 OK). In fase 2 il
  servizio ripubblica ogni ~2 s; se il servizio è giù la plancia mente. Riproduzione: servizio Safe spento, «avvia in
  prova» su Safe base, rileggere la plancia. Per proseguire, il banco ha costruito Safe da `control.params`
  (dichiarato nei passi).
- **R-E2E-2 — i 4 bot tennis erano `stopping` dal 24/09 16:06** (nessun servizio li chiude ad app spenta): la
  Control Room mostra «sta fermandosi» e NON offre «avvia» (P19). Si sblocca solo all'avvio dell'app (`ripresa_ponte`;
  commit `6ac2543` R2). La §5.1 del piano li porterebbe a `stopped` a mano: NON fatto (il ripristino riporta alla
  fotografia).
- **R-E2E-3 — nessuna traccia in `betfair_live_audit` dei cambi di «Ordini reali» e del freno** (ultimo id 96 del
  10/07 prima e dopo P26/P27). Resta solo `order_mode_updated_at/by` sulla riga (per il freno solo `updated_at`).
- **R-E2E-4 — `order_mode_updated_by='service_role'`** nel test: artefatto del client di servizio; la verifica con
  l'email del proprietario è di fase 2.
- **R-E2E-5 — due proposte `proposed` del 24/09 aperte**: `omega_manual_requests` 49 (cashout paper, trade 115) e
  `safe_strategy_requests` 257 (place modello paper). Non toccate. Alla fase 2 compariranno nelle schede: decisione
  dell'utente (ignorarle dalla UI prima dell'accensione?).
- **R-E2E-6 — atlante hazard VUOTO**: `hazard_atlas` 0 righe (non solo `hazard_atlas_leghe`, già noto da admin-26).
  Mike/Safe/Omega leggono `hazard_atlas` (inventario C263): in fase 2 attese note «atlante assente/v3».
- **R-E2E-7 — pg_cron `make-daily-post-job`** (09:00 ogni giorno, HTTP a una Edge Function del progetto) non è
  nell'inventario né nel piano.
- **R-E2E-8 — `omega_requests` (C211) non esiste** sul DB e nessun codice la usa: riga d'inventario da correggere.
- **R-E2E-9 — `betfair_refresh_requests` id 7 `pending` dal 01/09** (coda pre-match vecchia, C264): nessun consumatore noto.
- **R-E2E-10 — uscite tennis senza comando ad app spenta**: `UsciteTennis` legge `stats.auto` del ponte, non la
  colonna `uscite_automatiche`; a bot fermo (o ponte giù) non c'è pulsante in Control Room.
- **R-E2E-11 — i pulsanti uscite rendono esplicito il default**: Omega `uscite_protezione` assente → dopo andata e
  ritorno `'avvisa_e_proponi'` scritto (equivalente per il servizio, sonda identica). Stesso schema per Mike/Safe/scalper.
- **R-E2E-12 — asimmetria degli stop**: solo `safe_stop` riporta `mode='paper'`; `omega_stop`, `mike_stop`,
  `tennis_bot_service_stop`, `scalper_auto_stop` non toccano `mode` (verificato su `pg_get_functiondef`). Un bot fermato
  in live resta `stopping/live` finché il servizio o l'avvio nuovo non lo riporta a paper; ogni riaccensione riscrive
  comunque la modalità.

**Correzioni al piano/inventario emerse** (non fatte): §1.2 `MOTORE_ORDINI_CANALE` e `SCALPER_CANALE` sono a 1;
P27/R3 e inventario C303 («kill-switch solo in Segui Live») superati da `RigaFreno` in Control Room (commit `6ac2543`
19:49, `cr-freno-*` non inventariati); righe di codice spostate (es. `activateOmega` `omega.ts:1243`, non 1236;
`omegaParamsPatch` `:1216`; `ATTESA_CONFERMA_MS` `PannelloBot.tsx:478`); il campo importo Omega è
`cr-importo-omega-min-stake` (i `_` diventano `-`); `scalper_activate` vuole `p_mode` di STRATEGIA (maker/bias/both);
inventario C123 «Mike default True» superato (ora false in servizio e UI).

---

## 6. P32 — il DB è tornato alla fotografia

- **Evento esterno**: alle **18:45:22.33826 UTC** l'utente ha applicato `migrations/uscite_manuali_default_2026-09-25.sql`
  (una sola transazione: stesso `updated_at` su tutte le righe). Tutti i ripristini dei percorsi erano già chiusi
  (ultimo: P01-P03 alle 18:41:53; elenco in `P32_netto_migrazione.txt`).
- **Cambiate dalla migrazione (ATTESE, non KO), prima → dopo** (`P32_confronto.json`, 14 valori / 7 righe grezze):
  `mike_control.params.uscite_automatiche` assente → false; `safe_strategy_control.params.uscite_automatiche` assente →
  {base,esatto,punta,tennis,model: false} (`tennis_exit_approval` già true, invariato); `scalper_service_control.params.uscite_automatiche`
  assente → false; `tennis_bot_service_control.uscite_automatiche` true → false su 4/4; `updated_at` di queste 7 righe →
  18:45:22.33826. La migrazione ha toccato anche TUTTE le righe `scalper_control` (25) e `tennis_bot_control` (9)
  (fuori dalle mie colonne di controllo: conteggi invariati).
- **Tutto il resto torna byte per byte**: `strumenti/p32_netto.py` applica alla fotografia iniziale esattamente le
  scritture della migrazione (righe 52-127) e confronta con `P32_finale`: **0 differenze**. `P32_finale` vs
  `fotografia_post_migrazione` (18:47): **0 valori, 0 byte**.
- Dopo la migrazione ho **rieseguito dalla fotografia nuova** i percorsi che usano quelle righe (P07-P10, P11-P18,
  P19-P21, P22-P24): tutti OK, ripristino 0/0 contro `fotografia_post_migrazione`. Code: 0 righe nuove, max id
  invariati; nessuna riga `pending` lasciata; nessuna riga per partita attiva.

---

## 7. Processi avviati/spenti

- `npx vite preview --port 4173 --strictPort --host 127.0.0.1` (permesso dell'utente), in `frontend/` del
  principale, servendo `frontend/dist`: node **PID 13468** (padre bash 33512). Spento con `Stop-Process 13468`;
  verifica: `Get-NetTCPConnection -LocalPort 4173` vuoto («porta 4173 LIBERA»). Log `e2e_fase1/vite_preview.log`.
- Processi brevi: `npx vitest run --config e2e_fase1/vitest.e2e.config.ts -t <Pxx>` (circa 20 esecuzioni in
  sequenza, mai in parallelo), `python strumenti/e2e.py|sonda.py|p32_netto.py|riassunto.py`, 1 `pytest`, 1 `vitest` normale.
- Alla fine (20:53): 0 processi python/electron/node del repo, 0 porte 47311-47338/4173 in ascolto.
- **Nessun bot acceso davvero**, nessun servizio, nessun ordine, `npm run build` NON rilanciata (dist già fresca).

## 8. File creati

- `AUDIT_2026-09-25/E2E_FASE1_ESITI_2026-09-25.md` (questo).
- `AUDIT_2026-09-25/e2e_fase1/`: `fotografia_iniziale.json`, `controllo_stabilita.json`, `fotografia_post_migrazione.json`,
  `sonda_iniziale.json`, `sonda_finale.json`, `Pxx_prima/dopo/ripristino/sonda/esito.json`, `C295_esito.json`,
  `FALSIFICAZIONE_P01_P03_esito.json`, `falsificazione_confronto.json`, `P32_finale.json`, `P32_confronto.json`,
  `P32_confronto_post_migrazione.json`, `P32_netto_migrazione.txt`, `vite_preview.log`.
- `AUDIT_2026-09-25/e2e_fase1/strumenti/`: `e2e.py`, `sonda.py`, `p32_netto.py`, `riassunto.py` e copia di
  `percorsi.e2e.test.tsx`, `clientVero.ts`, `vitest.e2e.config.ts`.
- `frontend/e2e_fase1/` (dove girano, fuori da `src/`): `percorsi.e2e.test.tsx`, `clientVero.ts`, `vitest.e2e.config.ts`.
- Junction (NON cartelle): `<worktree>/.venv` → `.venv` del principale; `<worktree>/frontend/node_modules` →
  `frontend/node_modules` del principale. Da togliere con `cmd /c rmdir` prima di `git worktree remove` (mai `--force`).

## 9. Comandi eseguiti (esito)

- `git fetch`, `git log` (base 5798754), `git status` finale: solo file nuovi non tracciati (OK).
- `Get-CimInstance Win32_Process`, `Get-NetTCPConnection` (inizio/fine): OK.
- SQL di sola lettura via MCP Supabase (progetto `dqbwaocvlzbxfrpacsac`): colonne, trigger (0), firme RPC,
  `pg_get_functiondef` (grep delle scritture), cron, publication, `verifica_b1()`, conteggi SCOPERTI: OK.
- `python strumenti/e2e.py foto|confronta|ripristina|imposta`: OK (le sole scritture = ripristini e 3 preparazioni
  dichiarate: `mike_control.status` stopping→stopped, `tennis_bot_service_control(tennis_flb).status` stopping→stopped,
  `tennis_bot_control(36063889,tennis_flb).status` stopping→stopped; tutte riportate alla fotografia).
- `npx vitest run --config e2e_fase1/vitest.e2e.config.ts -t …`: 16 percorsi OK; 3 giri rossi per errori del BANCO
  poi corretti (P05 asserzione troppo stretta; P11 lettura degli effettivi → R-E2E-1; P22 corsa sul registro RPC +
  `p_mode` della card), 1 giro rosso VOLUTO (falsificazione).
- `pytest` registro/contratto (43 passed), `vitest valutaProposta.banda.test.ts` (20 passed).
