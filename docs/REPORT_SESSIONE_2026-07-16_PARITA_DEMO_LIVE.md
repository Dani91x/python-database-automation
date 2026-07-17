# REPORT SESSIONE 16/07/2026 — Parità DEMO/LIVE su tutta la piattaforma

> Documento di riferimento per riprendere il lavoro e rispondere a domande.
> Commit pushati su origin/master: `de0fc53` → `39e4c6b` → `3bbcbca` → `78d8d4d`.
> Gate finali: **1354 pytest + 752 vitest**, tutti verdi.
> ⚠️ AZIONI PENDENTI UTENTE: riavviare i runner calcio/tennis e l'exe omega
> (keepAlive, auto-recovery recorder e paper flumine attivi solo al riavvio) + E2E ladder.

---

## 0. Il principio (mandato utente)

**DEMO = LIVE senza soldi.** Ogni bot, quando attivato in demo, deve rispettare
l'intero flusso di lavoro reale — coda ordini, liquidità, betDelay, protezioni
ESEGUITE, P&L da fill — con l'unica differenza che non piazza ordini reali.
Operazioni visibili sul ladder. Fill conservativi: il demo può sottostimare il
live, mai illudere. Stack unico: flumine 2.13.11 + betfairlightweight 2.23.2
(deciso: NO migrazione a NautilusTrader, resta il riferimento di qualità).

## 1. Cosa è stato consegnato (per commit)

### `de0fc53` — Overhaul calcio+tennis (altro agente, controcheckato da me)
- Ladder v2: LAY a sinistra / BACK a destra, migrazione profili localStorage.
- Popup conferma ordine con proiezione P&L; 1-CLICK anche in PAPER (regola specchio).
- Deep-link Omega → Dashboard/Trading con ritorno.
- PAPER tennis di prima classe (ordini bot simulati sul ladder, latenza 3s).
- Realtime WS ovunque (migrazione `realtime_orders_bots.sql`, fallback poll legacy).
- 29 fix audit LIVE TRADING calcio (2 CRITICAL: bracket senza stop, TP mai scattante)
  + 14 fix bot tennis (greenup implementato da zero, restart solo a bot flat).
- Controcheck mio: 4 verificatori adversariali → tutti gli invarianti confermati;
  2 difetti trovati e fixati da me (grazia 180s sul restart tennis; unit test
  placeProjection). Report originale: `CONTROCHECK_REPORT_2026-07-16.md` (non tracciato).

### `39e4c6b` — DEMO = paper flumine vero per la famiglia scalper calcio
- `scalper_session.py`: `control.dry_run` = toggle demo/live. DEMO → client flumine
  `paper_trade=True` (SimulatedExecution sul flusso live) e strategie PIENE
  (`params["dry_run"]=False`): ordini simulati con ciclo completo, protezioni
  eseguite, contatori (colpi/green/scratch) e P&L da fill reali. Mai più dry-fire.
- Theta: PIENO in demo (simulato), MAI reale in live (`_theta_dry_run`, verdetto S4).
- `_handle_flumine_crash`: sweep REST d'emergenza SOLO in LIVE (in paper avrebbe
  cancellato ordini REALI di altri processi sul conto — market-wide).
- Mirror ordini sessione → `betfair_live_orders` → ladder (SOLO ordini, mai
  posizioni; MAI riconciliazione per bet_id: i bet_id simulati non sono univoci).
- `pnl_settled` tennis (pro+scalper, additivo, dedup).
- Review doppia: 2 HIGH trovati e fixati (hijack mirror per bet_id; dedup pro).

### `3bbcbca` — Omega su flumine, recorder, best practices, certificazione
- **Omega paper via flumine (v1)**: gate fail-closed (paper + `execution_mode=auto`
  + evento STREAMING + runner vivo in PAPER ≤90s) → enqueue sulla coda
  `betfair_live_order_requests` (idempotente `omega-t<id>`), riserva reserve-first,
  conferma coi fill SIMULATI reali, TTL 45s quasi-FOK con cancel del residuo,
  fallback legacy dichiarato (mai bloccati senza runner). **LIVE omega byte-identico**
  (REST FOK + riconciliazione, intoccati). Fix review: marker `flumine_client_ref`
  persistito PRIMA dell'enqueue + recovery per client_ref (crash window F1);
  aggregati contano i pending flumine (`max_events` non aggirabile, F2); età non
  calcolabile = hard deadline (mai zombie, F4). COSTITUZIONE_OMEGA §6-bis aggiornata.
- **Recorder certificato**: diagnosi 12/42 registrazioni complete (29%). Root cause
  incidente 16/07: keepAlive solo nel loop idle → stream muto 1,5h con runner vivo.
  Fix: keepAlive ANCHE in streaming (480s), stallo→auto-recovery subscription
  (throttle 900s) CON guardia money-critical (mai restart con ordini vivi/regole
  armate), marker copertura `.recmeta.jsonl` (raw byte-identico), utility
  `python -m Betfair.stream.tools.validate_recordings` + guardia nei backtest
  (default warning-only; `params['min_coverage']` per filtrare).
- **Best practices Betfair**: `docs/BETFAIR_BEST_PRACTICES_2026-07.md` (limiti
  ufficiali con fonti + assessment + 10 raccomandazioni). Quick-win applicati:
  keepAlive 10' nelle sessioni scalper (token .it scade in 20'!), soglia allerta
  200 mercati/subscription, `betfairlightweight[speed]` (ciso8601+orjson).
- **Certificato di fedeltà paper** (`test_flumine_paper_fidelity_2026_07_16.py`,
  26 test sul flumine installato): vedi §3.
- `pnl_settled` anche su scalper/sniper/theta calcio.

### `78d8d4d` — Fix della seconda review avanzata (cross-area)
- Il mirror delle sessioni scalper immetteva ordini bot nello specchio che
  **xhedge_worker** aggregava ciecamente → l'auto_hedge del risk engine avrebbe
  piazzato coperture REALI dimensionate sull'esposizione dei bot. Fix
  status-quo-ante: l'xhedge considera SOLO gli ordini della coda
  (`client_order_ref` che inizia per `awlq` = manuali + omega). +2 test.

## 2. Stato demo/live per bot (dopo questa sessione)

| Bot | Demo | Ladder | P&L |
|---|---|---|---|
| Motore live calcio (manuale+risk engine) | ✅ paper flumine (già prima) | ✅ | settlement |
| Scalper/Sniper/Theta calcio | ✅ paper flumine PIENO (era snapshot) | ✅ mirror nuovo | locked + `pnl_settled` |
| Tennis scalper/swing/pro/flb | ✅ paper flumine + latenza 3s | ✅ | locked + `pnl_settled` |
| Omega auto+manuale+missioni | ✅ paper via coda flumine (gate+fallback) | ✅ via coda | settlement (netto commissione) |

## 3. CERTIFICATO DI FEDELTÀ PAPER (cosa garantisce DAVVERO flumine 2.13.11)

GARANTITO: betDelay in-play REALE (sleep del delay dal marketDefinition, poi match
sul book corrente), coda/PIQ dal volume realmente scambiato (fill mai regalati),
place_latency, zero chiamate ordini all'exchange con `paper_trade=True`.

GAP DOCUMENTATI (pinnati nei test):
1. Solo il 50% del traded consuma la coda (conservativo → demo sottostima i fill).
2. PIQ senza cancellazioni stimate (ancora conservativo).
3. Fill aggressivo al place non depaupera il ladder condiviso (ottimistico con
   più ordini simultanei).
4. ⚠️ **P&L simulato LORDO** — flumine non applica la commissione: i `pnl_settled`
   vanno letti al lordo del 4,5-5%. Su scalp da 1 tick può flippare l'EV.
   DECISIONE APERTA: nettare `pnl_settled` a livello mercato o leggerlo lordo.
5. betDelay snapshottato alla creazione del package (transizione pre→in-play).
6. In paper il place riesce sempre (niente rifiuti API/latenza variabile).
MAI attivare `simulation_available_prices=True` (regalerebbe i fill).

## 4. Limiti noti ACCETTATI (dichiarati, non bug)

- Omega TTL 45s = semantica quasi-FOK (il live usa FOK vero); fallback a hard
  deadline conferma a size piena (≡ comportamento legacy).
- `validate_recordings`: finestra attesa [KO, KO+115'] sotto-copre i supplementari.
- Registrazioni storiche parziali restano parziali (ora però i backtest lo SANNO).
- Tennis `dry_run=True` per-bot resta una modalità degradata (default corretti per
  modalità); pnl_settled in LIVE resta 0 (verità live = cleared Betfair).
- Bleed di superficie: gli ordini omega/scalper appaiono nella UI calcio dello
  specchio (voluto: ladder); l'xhedge li esclude (78d8d4d).

## 5. Cosa resta da fare (unico punto escluso: scala 1000)

- **Punto 5 — scala 1000+ eventi/giorno da settembre**: direzione in
  `docs/BETFAIR_BEST_PRACTICES_2026-07.md` (sezione piano scala). Chiave:
  consolidare le sessioni scalper per-evento (1 processo+login+stream ciascuna →
  tetto ~10 connessioni stream/app key), subscription dinamiche, batch Supabase.
- Decisione aperta: commissione su `pnl_settled` (vedi §3.4).
- Paper n≥40 del cecchino: ora i numeri sono credibili (paper vero) — raccogliere.
- Checklist pre-privatizzazione repo (nota: il repo è PUBBLICO e il push del 16/07
  è stato confermato esplicitamente dall'utente).

## 6. File chiave (per ritrovare le cose)

- Sessione scalper paper+mirror: `Betfair/stream/scalper/scalper_session.py`
- Omega flumine: `Betfair/omega/omega_service.py` (gate/enqueue/poll ~r.400-750),
  `omega_db.py`, `omega_config.py`, `COSTITUZIONE_OMEGA.md` §6-bis
- Recorder: `Betfair/stream/raw_listener.py`, `runner.py` (heartbeat_worker),
  `Betfair/stream/tools/validate_recordings.py`
- Certificato paper: `Betfair/stream/tests/test_flumine_paper_fidelity_2026_07_16.py`
- Best practices: `docs/BETFAIR_BEST_PRACTICES_2026-07.md`
- Fix xhedge: `Betfair/stream/xhedge_worker.py`
