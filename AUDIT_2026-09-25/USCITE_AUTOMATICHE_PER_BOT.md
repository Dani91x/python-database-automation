# USCITE AUTOMATICHE PER SINGOLO BOT — referto del delegato (25/09/2026)

Ordine dell'utente (testuale): «Tutti i bot (in live e in paper) DEVONO AVERE L'ABILITAZIONE per le
uscite automatiche e per l'operatività totalmente automatica; se disattivo il pulsante (TUTTO DEVE
ESSERE IN UI PER SINGOLO BOT), le uscite le gestisco io manualmente tramite l'apposita scheda».

Worktree su base `372158e`, **rebased su `c5c8a92`** (origin/master, fix mercato combo/ref tennis/Omega stato mancante): applicazione pulita, nessun conflitto, righe dei fix NON toccate; test rilanciati dopo il rebase (§5). Niente commit, niente push, nessuna scrittura sul DB, nessun processo
nuovo, nessun replay lanciato. Bot tennis (`Betfair/stream/tennis_live/**`) NON toccati.
Patch completa: `AUDIT_2026-09-25/uscite_automatiche.patch` (+ i file nuovi elencati in §4).

## 1. Principio (uguale per tutti i bot)

- **Una chiave per servizio, letta a caldo a ogni giro, identica in paper e live** (nessuna tabella
  nuova, nessun canale nuovo, nessun processo nuovo). Default = comportamento di OGGI: al primo
  avvio con questo codice non cambia niente.
- **Cambia solo CHI esegue l'uscita**: la decisione della strategia è calcolata come sempre, poi un
  cancello («gate») la esegue (acceso) o la trasforma in PROPOSTA (spento). Soglie, stake, gambe,
  timer: invariati. I timer continuano a correre (Mike: `live_since` e prezzo d'ingresso si
  applicano anche con l'uscita bloccata — test `test_spento_la_finestra_del_fischio_corre...`).
- **Protezioni sempre automatiche**: stop/cap, fine mercato/regolamento, riconciliazione, annulli,
  flatten di residui «mai nudi», kill-switch, completamento di un'uscita già partita/approvata.
- **Approvare** = il bot esegue ESATTAMENTE la decisione che la strategia ha in quel momento
  (Safe/Omega: percorso `proposed → pending` di sempre; Mike: firma nel contesto della partita).
  **Chiudere a mano** = il «Chiudi» di sempre della riga/partita.

| Bot | Chiave | Default (= oggi) | Dove si vede/cambia in UI |
|---|---|---|---|
| Omega | `omega_control.params.uscite_protezione` (`automatico` / `avvisa_e_proponi`) — GIÀ ESISTENTE dal 24/09 | `avvisa_e_proponi` = **manuali** | riga Omega della plancia (nuovo) + `OmegaParamsSheet` (esistente) |
| Mike | `mike_control.params.uscite_automatiche` (bool) | `true` | riga Mike (nuovo) + `MikeParamsSheet` gruppo «uscite» (nuovo campo) |
| Safe base/esatto/punta/model | `safe_strategy_control.params.uscite_automatiche.{base,esatto,punta,model}` | `true` | riga della strategia (nuovo) |
| Safe tennis | `...uscite_automatiche.tennis`, ripiego sul cancelletto storico `tennis_exit_approval` | `not tennis_exit_approval` (valore del DB) | riga Safe tennis (nuovo) + scheda parametri (spunta storica, ora riallinea la mappa) |
| Scalper calcio | `scalper_control.params.uscite_automatiche` di ogni sessione attiva | `true` | riga Scalper (nuovo, scrive su tutte le sessioni attive) |
| Safe «a mano», 4 bot tennis | — | — | nessun interruttore qui («a mano» non ha uscite del bot; tennis = altro delegato) |

Stato mostrato sulla riga (testi esatti, vitest): `uscite: automatiche` · `uscite: manuali — N
posizioni aperte da X min` · `uscite: non lette` (nessun pulsante, fail-closed); pulsante `passa a
manuali` / `passa ad automatiche`.

## 2. Tabella bot × uscita × classificazione × prima → dopo

Legenda: **D** = discrezionale (sotto l'interruttore) · **P** = protezione (sempre automatica).

### Omega (nessun codice backend cambiato: verificato, già conforme)
| Uscita | file:riga | Cl. | Oggi | Dopo |
|---|---|---|---|---|
| Proposte d'uscita v3/v4: `blocca_il_profitto`, `protezione`, `cap`, `rischio` | `Betfair/omega/omega_proposte.py:80` (motivi), `:250` `modo_uscite`, `:436` esecuzione se `automatico` | D (per ordine utente 17/09 «sia in profit che in loss») | `uscite_protezione` decide; default manuali | invariato; ora anche dalla riga della plancia |
| Green-up automatico v2 | `omega_service.py:5769` `_greenup_active`; spento d'ufficio con `strategy_version>=3` in `omega_config.py:382-393` | D | spento in v3 (default `strategy_version=3`, `omega_config.py:214`) | invariato — **limite**: con `strategy_version=2` l'interruttore NON lo governa (lo governa `greenup_mode`) |
| Cash out dell'utente | `omega_service.py:5351` `_manual_cashout` | utente | manuale | invariato |
| Regolamento, riconciliazione, annullo ordini vivi, sorveglianza posizione di conto | `omega_service.py:4353`, `:3721`, `:4208`, `:4074` | P | automatiche | invariato |
| Lettura a caldo | test esistente `test_omega_uscite_protezione_2026_09_24.py::test_lettura_a_caldo_dal_run_once` (20/20 verdi) | | | |

### Mike
| Uscita | file:riga (engine.py dopo la patch) | Cl. | Oggi | Dopo (spento) |
|---|---|---|---|---|
| Green take-profit pre-match (resting/taker, ultimo ingresso in profitto) `under_green` | `:2651` (`_after_entry_fill`), `:2576`, `:2593`, `:2626` | D | auto | proposta `green_pre|cN`; lo stato (PRE_OPEN) e il prezzo d'ingresso si applicano |
| Uscita al fischio `ko_green` (+N tick, finestra) | `:2945` | D | auto | proposta `ko_green|cN`; `live_since`/finestra corrono; a finestra scaduta la strategia passa alla copertura e la proposta DECADE |
| Cash out a soglia / cash out intelligente `under_close`+`over_close` | `:3331`, `:3340` | D | auto | proposta `chiusura|cN`, stato resta LIVE_COVERED (mai LIVE_CLOSING senza ordini), `bloccabile` = netto commissione |
| Uscita in perdita a modello / tollerata (HT, 2T) | `:3370`, `:3379` | D (**dubbio 1**) | auto | proposta `urgente: true` |
| Cap perdita partita `event_loss_cap_pct` (`close_reason='loss_cap'`) | `:3385` | P | auto | auto (test `test_spento_il_cap_perdita_partita_chiude_lo_stesso`) |
| Green / uscita a tempo del re-ingresso `reentry_green` | `:3534`, `:3563`, `:3584`, `:3608` | D | auto | proposta `reentry_green|cN` |
| Copertura Over 4.5 `over_cover` (piena, a tranche, seconda tranche) | `:3200`, `:3298` | P (**dubbio 2**) | auto | auto (test `test_spento_la_copertura_over_45_parte_lo_stesso`) |
| Riprezzo/residuo di una chiusura già partita (LIVE_CLOSING, PRE_GREEN_PENDING, REENTRY_GREEN_PENDING, o gamba dello stesso ruolo già nel ciclo) | `:2203`, `:2237` | P (completamento) | auto | auto |
| Regolamento a mercato chiuso, annulli, chiusura manuale (`manual_close`, C2), chiuso dall'utente | `:2377`, `_decide_flatten :2052` | P / utente | auto | auto (il gate non li vede: ritornano prima o non sono uscite del motore) |

Gate: `engine.gate_uscite` `:2282`, chiamato come ultima parola di `decide` `:2185`; costanti
`USCITE_DISCREZIONALI :2194`, `MOTIVI_PROTEZIONE :2198`, `STATI_USCITA_IN_CORSO :2203`,
`APPROVAZIONE_TTL_S = 120 s`. Campi persistiti `MatchCtx.uscita_proposta/uscita_approvata` (`:330`)
in `service._CTX_FIELDS` (`service.py:270-275`). Approvazione: richiesta `approva_uscita`
(`service.py:2370`, `_request_approva_uscita :2431`: chiave diversa → `rejected/proposta_cambiata`,
nessuna proposta → `rejected/proposta_non_viva`), telemetria loggata solo al cambiamento
(`service.py:3642-3647`). Parametro `config.py:238`. Proposta = `{chiave, categoria, ciclo, stato,
stato_voluto, motivo, close_reason, ordini[{ruolo,mercato,selezione,lato,prezzo,size}], bloccabile,
urgente, minuto, gol, decided_at (fermo per chiave), proposed_at, sostanza}` in `mike_events.ctx`
(nessuna colonna nuova; scritta solo quando cambia la sostanza → respiro DB).

### Safe (base / esatto / punta / tennis / modello)
| Uscita | file:riga | Cl. | Oggi | Dopo (spento per quella strategia) |
|---|---|---|---|---|
| Regole del manuale base (`loss` sfavorita pareggia, `profit` favorita segna, `red_card`, controllo passato, `time` minuto) | `exits.py:949-965` | D (**dubbio 1** per `loss`/`red_card`) | auto | proposta (stesso corpo del cancelletto tennis, `urgente` per loss/red/mandatory) |
| Esatto (`loss` lato bancato segna, `time`) | `exits.py:968-975` | D | auto | proposta |
| Punta (`loss`, `profit`, `time`) | `exits.py:978-987` | D | auto | proposta |
| Tennis (`mandatory` due game persi, `profit`, `loss`) | `exits.py:990-1015` | D | proposta se `tennis_exit_approval` (14/09) | invariato: stessa proposta, ora comandata anche dalla riga |
| Uscite a modello dei trade `model` (take-profit, cash-out quasi gratis, linea decisa contro, evento avverso) | `exits.py:1163-1210`, `bot_service.py:4175` | D | auto | proposta (chiave `model`) — **non provato end-to-end, v. §6** |
| Residuo di un'uscita già inviata/approvata | `bot_service.py:3676` | P (completamento) | auto | auto (non ripassa dal cancello) |
| Chiusura solidale della combo (`forced`, con la guardia mercato di `c5c8a92`) | `bot_service.py:3836` | P | auto | auto |
| Svolgimento combo incompleta (gambe fillate di una combo fallita) | `bot_service.py:8015` | P | auto | auto |
| Settlement, riconciliazione, kill-switch REST, feed cieco | invariati | P | auto | auto |

Cancello generalizzato: `bot_service.py:3782-3808` (era solo tennis). Risoluzione:
`normalize_uscite_automatiche :417`, `uscite_automatiche_di :438`, in `resolve_params :356` (la mappa
vince e riallinea `tennis_exit_approval`), esposta in `params_effective :527`, default `:160`.
Riaccese con proposta viva → la proposta DECADE col motivo e il bot esegue (prima il marcatore
restava sulla riga; bug trovato dal test e corretto: `meta` riallineato prima di `_send_exit`).

### Scalper calcio
| Uscita | file:riga (scalper_bot.py) | Cl. | Oggi | Dopo (spento) |
|---|---|---|---|---|
| Chiusura a +scalp_ticks (target) dopo il fill | `_open_lock :1825` | D | auto | nessuna chiusura; LOCKING senza close; evento `uscita_proposta` (una volta) |
| Gamba opposta del maker che diventa la chiusura | `_manage_maker :1346`, `:1388` | D | auto | la gamba opposta si RITIRA e si propone (via `_open_lock`) |
| Scratch a pari | `:1706-1722` | D | auto | proposta `scratch`, niente ordini |
| Stop a N tick / `lock_ttl` → flatten | `:1677` | P (**dubbio 3** su `lock_ttl`) | auto | auto (test) |
| Flatten del residuo / fill durante cancel («mai nuda»), pre-KO, force-flat, cap evento, riconciliazione | `:702`, `_handle_cancelling`, `scalper_session.py` | P | auto | auto |
| Riaccese | `:1622-1628` | | | il bot rimette la SUA chiusura calcolata dal fill |

Lettura a caldo: `scalper_session.py:1155-1158` (stessa lettura del battito 5 s, ora `status,params`:
`control_stato_e_params :475`, `applica_uscite_automatiche :431`), whitelist UI `:70-72`; specchio
nel finto del banco `tools/replay_registrazioni.py:513` (stessa firma, altrimenti il replay dello
scalper si sarebbe rotto). **Approvazione della singola chiusura NON implementata** (v. §5, dubbio 4).

## 3. Migrazioni (ordine di applicazione, additive, idempotenti)

1. `migrations/uscite_automatiche_mike_2026-09-25.sql` — allarga il CHECK `mike_requests.kind` con
   `approva_uscita` (toglie i CHECK su `kind` con qualunque nome, rimette quello allargato) e la RPC
   `mike_request` (stesse grant; `approva_uscita` pretende `chiave`). Nessun dato toccato.
2. `migrations/uscite_automatiche_scalper_2026-09-25.sql` — RPC owner-only
   `scalper_uscite_automatiche(p_automatiche boolean) → integer` che scrive la chiave su TUTTE le
   sessioni attive (`requested/arming/armed/running`).
3. Omega, Safe: **nessuna migrazione** (chiavi dentro `params` JSONB; RPC `*_update_params` esistenti).

Senza la (1) il bottone «approva uscita» di Mike fallisce con «kind non valido» (nessun effetto sul
bot). Senza la (2) il pulsante della riga Scalper fallisce (errore mostrato, nessun effetto).

## 4. Modifiche (file:riga) e file nuovi

Backend: `Betfair/mike/config.py:231-238`; `Betfair/mike/engine.py:322-331, 2181-2366`;
`Betfair/mike/service.py:270-275, 2277-2279, 2370-2371, 2431-2462, 3642-3647`;
`Betfair/safe_strategy/bot_service.py:151-160, 352-358, 411-452, 525-528, 3782-3808` (numeri dopo il rebase);
`Betfair/stream/scalper/scalper_bot.py:206-208, 434-446, 1341-1346, 1388, 1622-1628, 1706-1722,
1825-1835, 1846-1860, 2498`; `Betfair/stream/scalper/scalper_session.py:70-72, 431-453, 475-488,
1155-1158`; `Betfair/stream/scalper/tools/replay_registrazioni.py:513-519`.
Contratti aggiornati (non ammorbiditi): `Betfair/mike/tests/test_mike_audit_2026_09_11.py:1106`
(kind `uscita_approvata` dichiarato), `Betfair/mike/tests/test_mike_certificazione_ui_2026_09_11.py:276`
(kind richiesta `approva_uscita`).

Frontend: `frontend/src/lib/interruttori.ts` (import `:50`; `cambiaUscite?` in
`ComandiInterruttori :667-673`; comando `:977-1001`; sezione pura `:1008-1180`: `StatoUscite`,
`statoUscite`, `usciteInterruttori`, `paramsConUscite`, `conPosizioniAperte`,
`usciteSessioniScalper`); `frontend/src/lib/scalperControlRoom.ts:131-146` (`impostaUsciteScalper`);
`frontend/src/lib/mike.ts` (kind richiesta `:17-19`, campo parametro `:490-492`, default `:560`,
4 kind attività + etichette + righe `:1195-1199, 1228-1232, 1391-1402`, codici `:1536, 1555-1557`);
`frontend/src/components/safestrategy/BotParamsSheet.tsx:814-824` (la spunta storica del tennis
riallinea la mappa); `frontend/src/components/controlroom/SchedaMike.tsx:42, 113-116` (monta la
proposta); `frontend/src/pages/ControlRoom.tsx:72-73, 286-287, 298-307, 575, 604`.

**Righe da fondere col delegato tennis (isolate, come richiesto):**
- `PannelloBot.tsx`: import `StatoUscite :48`; prop `uscite` `:262-268` e destrutturazione `:274`;
  passaggio a `RigaBot :428`; firma `RigaBot :485, :489`; blocco «uscite» `:677-714` (unico blocco
  JSX nuovo, prima degli importi).
- `interruttori.ts`: solo aggiunte (sezione 25/09 in coda a `creaInterruttori` e dopo di essa); per i
  bot tennis `statoUscite` → `null` e `cambiaUscite` → `UsciteNonGestiteQui` (il loro interruttore
  lo fa l'altro delegato: basta estendere `statoUscite`/`paramsConUscite`).
- `useControlRoom.ts`: import `:113-114` e `rigaScalper` `:2001-2004` (i «params» della riga scalper
  = aggregato delle sessioni attive).

File nuovi: `migrations/uscite_automatiche_mike_2026-09-25.sql`,
`migrations/uscite_automatiche_scalper_2026-09-25.sql`,
`frontend/src/components/controlroom/PropostaUscitaMike.tsx`,
test `Betfair/safe_strategy/tests/test_uscite_automatiche_2026_09_25.py` (18),
`Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py` (23),
`Betfair/stream/tests/test_scalper_uscite_automatiche_2026_09_25.py` (13),
`frontend/src/lib/interruttoriUscite.test.ts` (17), `frontend/src/components/controlroom/PannelloBotUscite.test.tsx` (9),
`frontend/src/components/controlroom/PropostaUscitaMike.test.tsx` (6),
sonde `AUDIT_2026-09-25/sonde/mutazioni_uscite_automatiche.py`, `.../mutazioni_uscite_frontend.py`.

## 5. Test e falsificazione

Sandbox: `SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x`.

| Suite | Esito |
|---|---|
| Safe nuovi (acceso=parità, spento→proposta con chiavi, paper e live identici, tennis mappa↔cancelletto, a caldo in entrambe le direzioni, approvazione→a mercato) | 18/18 |
| Safe intera `Betfair/safe_strategy/tests` (modulo toccato) | prima del rebase 1537 verdi; **dopo il rebase su c5c8a92: 1541 verdi, 3 skip, 1 xfail, 0 rossi** |
| Mike nuovi (motore + servizio intero `run_once`: proposta persistita, approvazione dalla coda, chiave cambiata rifiutata, a caldo, parità) | 23/23 |
| Mike intera `Betfair/mike/tests` | 859 verdi (836 esistenti + 23), uguale dopo il rebase |
| Scalper nuovi | 13/13 |
| Scalper nuovi + esistenti (bot, audit, certificazione, control room, cli guardia, mission, pnl, presize, sniper, freno, submin, banco comune) | dopo il rebase 222 verdi, 10 skip (preesistenti: registrazioni assenti) |
| Omega `test_omega_uscite_protezione_2026_09_24.py` (non modificato) + `test_realtime_contratto_2026_09_12.py` dopo il rebase | 25/25 |
| `Betfair/test_realtime_contratto_2026_09_12.py` + Safe c3/scheda/eta | 158 verdi, 1 skip |
| vitest nuovi (17 + 9 + 6) e toccati (PannelloBot, PannelloBotScalper, interruttori, interruttoriScalper, mike, omega, contratto consapevolezza, BotParamsSheet, scalperControlRoom, useControlRoom x3, righeBot, comandiBot, soloTennis, SchedaPartita, SchedaMike, pagine ControlRoom/Mike/SafeStrategy, MikeParamsSheet) dopo il rebase | 24 file, 653 verdi, 1 skip |
| `npx tsc -p tsconfig.app.json --noEmit` | 0 errori |

Falsificazione (mutazione del codice di produzione → test rossi; ripristino dalla copia in memoria
verificato byte per byte; riproducibile con le due sonde):
S1 cancello Safe mai attivo → 6 rossi · S2 niente decadenza alla riaccensione → 1 · S3 mappa ignorata
→ 8 · M1 gate Mike sempre aperto → 12 · M2 cap perdita non protezione → 1 · M3 uscita in corso non
riconosciuta → 3 (prima mutazione VERDE: il criterio «stato» era coperto solo dall'altro criterio;
aggiunti 4 test che lo isolano) · M4 approvazione ignorata → 2 · M5 proposta non persistita → 4 ·
M6 stato di chiusura senza ordini → 2 · M7 timer buttati → 2 · M8 approvazione su chiave sbagliata
→ 1 · C1 target parte comunque → 5 · C2 maker usa la gamba opposta → 1 · C3 scratch parte → 1 ·
C4 sessione non applica → 1 · C5 riaccendere non rimette la chiusura → 1 · F1 pulsante manda il
valore sbagliato → 2 · F2 tennis non riallinea il cancelletto → 1 · F3 Omega «automatico» da
qualunque valore → 2 · F4 approva senza chiave → 1 · F5 bottone vivo col feed fermo → 1.

Finti: Safe `FakeDB/FakeMarket` di `test_bot_service.py`; Mike classi VERE del motore + `FakeDB`
di `test_mike_service.py` (events con `ctx`/`positions`, requests `id/kind/payload/status/result`);
scalper `_FakeOrder/_FakeMarket` di `test_scalper_presize_2026_07_11.py`; sessione: finto con la
firma di `Db.log`; frontend: proposta con le chiavi di `gate_uscite`.

## 6. Replay (NON lanciati: PC condiviso) — comandi ed esiti attesi

Uno per bot, in sequenza (ordine del 24/09), con interruttore ACCESO (default = come c3j/c3k):
```
python -m Betfair.stream.backtest.certifica mike --scenari tutti --worker 1 --diario AUDIT_2026-09-25/diario_mike_uscite.txt
python -m Betfair.stream.backtest.certifica safe_base --scenari tutti --worker 1 --diario AUDIT_2026-09-25/diario_safe_base_uscite.txt
python -m Betfair.stream.backtest.certifica safe_esatto --scenari tutti --worker 1 --diario AUDIT_2026-09-25/diario_safe_esatto_uscite.txt
python -m Betfair.stream.backtest.certifica safe_punta --scenari tutti --worker 1 --diario AUDIT_2026-09-25/diario_safe_punta_uscite.txt
python -m Betfair.stream.backtest.certifica safe_tennis --scenari tutti --worker 1 --diario AUDIT_2026-09-25/diario_safe_tennis_uscite.txt
python -m Betfair.stream.backtest.certifica omega --scenari tutti --worker 1 --diario AUDIT_2026-09-25/diario_omega_uscite.txt
python -m Betfair.stream.backtest.certifica scalper_calcio 35797769 --scenari tutti --worker 1 --diario AUDIT_2026-09-25/diario_scalper_uscite.txt
```
Attesi (parità con c3j/c3k del 24/09): Mike 15/15, 0 violazioni; Safe base/esatto/punta 22/22, 0
violazioni; Safe tennis 34+2 con le stesse T7/T7-APPROVAZIONE preesistenti (~77); Omega 19/19 per
partita, 0 violazioni (azioni identiche, scarti di tick sui tempi di stop come ieri); scalper su
35797769: stesse 102-108 azioni e gli stessi reperti S5/S3 preesistenti (il finto del banco ora
espone anche `control_stato_e_params`). Per Omega/Mike/Safe/scalper il codice con interruttore
acceso è identico al precedente (parità provata nei test); il replay la conferma sul servizio intero.
Scenari NUOVI suggeriti (non scritti: toccano il registro del banco, fuori perimetro): «uscite-manuali»
per Mike/Safe/scalper con l'interruttore spento → attesi: zero uscite discrezionali eseguite,
proposte scritte, protezioni eseguite.

## 7. Dubbi da confermare con l'utente

1. **Uscite in perdita della strategia (Mike loss HT/2T a modello e tollerata; Safe `loss`/`red_card`/
   `mandatory`)**: le ho messe SOTTO l'interruttore (proposte, marcate urgenti), coerenti con gli
   ordini del 14/09 (tennis) e del 17/09 (Omega «sia in profit che in loss») e con il default di oggi
   del tennis. La regola del coordinatore dice «stop sempre automatici»: se l'utente vuole le uscite
   in perdita sempre automatiche basta aggiungere il motivo a `MOTIVI_PROTEZIONE` (Mike,
   `engine.py:2198`) e, per Safe, escludere quei `kind` dal cancello (`bot_service.py:3793`). Per
   Mike il vero stop (`event_loss_cap_pct`) è già protezione.
2. **Copertura Over 4.5 di Mike**: classificata PROTEZIONE (automatica sempre). Motivo: non chiude la
   posizione, la assicura contro il 4° gol; è la gamba che rende la strategia a rischio limitato;
   sospenderla in attesa di un clic lascia l'Under nudo nel momento più pericoloso. Confermare.
3. **Scalper `lock_ttl_ms` (1 h)**: è un'uscita a tempo; l'ho tenuta PROTEZIONE (timeout di
   sicurezza, stessa via dello stop). Confermare.
4. **Scalper: niente «approva» della singola chiusura**. Spento, la posizione resta con stop e
   protezioni; l'utente chiude con lo stop sessione (force-flat) o riaccende l'interruttore (il bot
   rimette la sua chiusura). Una firma per singola chiusura a +1 tick passerebbe da un giro DB di 5 s:
   non è la stessa uscita. Serve una decisione: basta così, o si vuole un «approva» per selezione?
5. **Scalper, sessioni armate DOPO il cambio**: la RPC scrive solo sulle sessioni attive; una sessione
   nuova nasce con le uscite automatiche (la riga lo dice: «nessuna sessione attiva: le nuove nascono
   con le uscite automatiche»). Se l'utente vuole che la scelta valga anche per le prossime serve un
   posto «per bot» (es. passarla in `scalper_activate` dalla pagina Segui Live).
6. **Omega v2 (`strategy_version=2`)**: il green-up automatico v2 non è governato da questo
   interruttore (lo governa `greenup_mode`). In v3/v4 (default) tutto passa dalle proposte.
7. **Mike, un'approvazione vale per l'uscita di QUEL ciclo e i suoi seguiti** (riprezzi,
   riappoggio dopo un annullo, residuo): per una seconda uscita diversa nello stesso ciclo con una
   gamba dello stesso ruolo già presente non si chiede una seconda firma. Scelta per non lasciare
   posizioni scoperte a metà; alternativa: firma per ogni ordine.
8. **Mike, proposta che «lampeggia»**: se la condizione della strategia oscilla (es. cash out
   intelligente sopra/sotto soglia) la proposta nasce e decade a ogni oscillazione (una scrittura e
   un'attività per cambio). Omega/Safe hanno un'isteresi; per Mike non l'ho aggiunta.

## 8. Cosa NON ho potuto verificare

- Replay (non lanciati per ordine); scenari «uscite manuali» nel banco non scritti.
- Migrazioni non applicate né provate su Postgres (scritte a mano; il nome del CHECK di
  `mike_requests.kind` è gestito con un DO che toglie ogni CHECK su `kind`).
- Uscite a modello dei trade `model` di Safe con interruttore spento: il cancello è lo stesso punto
  di codice (dopo `_decide_model_exit`) ma nessun test end-to-end con un trade `model`.
- Percorso live REST reale di approvazione Mike (`approva_uscita` → gamba live): provato solo in
  paper con `run_once`; il motore è identico in live (il gate non legge la modalità).
- UI in app reale (niente `npm run build`, niente app avviata); vitest + tsc soltanto.
- Scalper con sniper/theta attivi: il gate copre solo `ScalperStrategy` (maker/join/bias), non
  `sniper_bot`/`theta_bot` che girano nella stessa sessione.
