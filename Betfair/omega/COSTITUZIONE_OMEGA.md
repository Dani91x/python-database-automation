# ⟶ COSTITUZIONE DEL BOT «OMEGA» ⟵
### Fonte unica di verità. Ogni riga di codice di Omega deve essere conforme a questo documento.
### v1.0 — 2026-07-12 · Betfair Exchange (.it) · Correct Score LAY · Set-and-forget

---

## 0. Cos'è Omega (in una frase)

Omega è un bot **set-and-forget** che ogni giorno conta le partite di calcio in
programma su Betfair, divide un **obiettivo giornaliero** (default €250) per il
numero di partite per ricavare il **profit-target per singola partita**, e su
**ogni** partita — quando entra nella sua **fascia oraria/minuto** — piazza **un
solo LAY** sul mercato **CORRECT SCORE**, scegliendo il risultato esatto **meno
probabile** con **quota entro un range configurabile** (non 600).

> Omega non fa scalping né trading continuo. Piazza **un ordine per match** e
> attende il **settlement del mercato Betfair** (verità ultima). Nessun'altra
> azione richiesta all'utente dopo lo START.

---

## 1. Principi non negoziabili (INVARIANTI)

1. **I1 — Un solo trade per match.** Per ogni `event_id` Omega piazza **al più un
   LAY** nella vita del bot. Idempotenza a più livelli, con pattern
   **RESERVE-FIRST**: (a) prima di piazzare si INSERISCE una riga `pending` in
   `omega_trades` — l'**unique index su `event_id`** fa da lock, anche
   cross-processo e **oltre** i 60s di de-dup Betfair; (b) solo dopo la riserva si
   esegue l'ordine (PAPER/LIVE) e si aggiorna la riga a `open` (fill) o `error`
   (nessun ordine reale attivo); (c) `customerRef` deterministico `omega-<event_id>`;
   (d) single-instance lock di processo (socket 127.0.0.1:47313). Così un ordine
   LIVE **non può mai raddoppiarsi né restare orfano**.
2. **I2 — PAPER prima, LIVE dopo.** Il default è **PAPER** (soldi finti su prezzi
   live reali). Il passaggio a **LIVE** (soldi veri) avviene **solo** con azione
   esplicita dalla UI (toggle mode → `live`). Nessun ordine reale è possibile
   finché `mode != 'live'`.
3. **I3 — Betfair è la verità.** Il P&L di un trade è determinato dal
   **settlement del mercato** (runner `WINNER`/`LOSER`), non da stime interne. Il
   settlement scatta SOLO quando ogni runner ha uno stato terminale
   (`WINNER/LOSER/REMOVED`): un `CLOSED` non ancora finalizzato viene ritentato,
   mai regolato a `void` per errore. Dopo un ordine LIVE la conferma DB è
   **robusta** (retry) e, se fallisce, si logga CRITICAL con il `bet_id` per la
   riconciliazione. Mai dedurre un incasso da un ordine non ancora regolato.
   🔴 **GATE LIVE**: la riconciliazione automatica via `listCurrentOrders`
   (`customerStrategyRef='omega'`) per righe `pending` residue (es. kill del
   processo a metà piazzamento) è **TODO** e va implementata PRIMA di operare in
   LIVE con importi reali. In PAPER il rischio è nullo.
4. **I4 — Nessun ricalcolo retroattivo del passato.** Il target per-match si
   ricalcola **solo in avanti** sui match ancora da piazzare; i trade già
   piazzati non si toccano.
5. **I5 — Owner-only.** Ogni RPC verso il DB passa da `betfair_live_is_owner()`.
   Le tabelle `omega_*` sono in RLS, `REVOKE ALL` da `anon/authenticated`.
6. **I6 — Fallimento sicuro.** Qualsiasi errore su un match (mercato assente,
   book vuoto, liquidità insufficiente, API down) **salta quel match** e prosegue;
   non blocca il bot né duplica ordini. Ogni salto è loggato in `omega_activity`.
7. **I7 — Idempotenza di stato.** Il servizio è un loop stateless-ricostruibile:
   riavviato, ricostruisce lo stato da `omega_control` + `omega_trades` senza
   ripiazzare nulla (I1).
8. **I8 — Trasparenza del rischio.** La dashboard mostra sempre la **liability
   aperta totale** e l'esposizione a coda. Omega non nasconde mai il rischio del
   «raccogliere spiccioli davanti al treno» (vedi §9).

---

## 2. La matematica (esatta)

Sia:
- `G` = obiettivo giornaliero (default **250 €**),
- `R` = profit **realizzato** finora oggi (somma P&L dei trade **settled**),
- `M` = numero di match **ancora eleggibili e non piazzati** (incluso quello corrente),
- `c` = commissione Betfair (default **0.05**),
- `O` = quota lay scelta per il match,
- `P` = profit-target per il match corrente.

**Target dinamico per match:**
```
P = (G − R) / max(M, 1)
```
Se `stop_on_goal = true` (default) e `R ≥ G` → Omega **non piazza più** (obiettivo
raggiunto). `P` è vincolato a `P ≥ 0`.

**Sizing del LAY** (backer stake `s` = ciò che incassi se il risultato NON esce):
```
s          = P / (1 − c)          # incasso netto commissione = P
liability   = s · (O − 1)          # ciò che perdi se il risultato ESCE
profit_win  = s · (1 − c)  = P     # per costruzione
profit_lose = − liability
```
Vincoli:
- `s ≥ min_stake` (LAY .it minimo **€0.50**). Se `s < min_stake` → `s = min_stake`
  (il profit supererà leggermente `P`).
- `s` arrotondato a `stake_rounding` (default 0.01); `O` arrotondata al **tick**
  valido Betfair (`round_to_tick`).
- Se `max_liability_per_match > 0` e `liability > cap` → si riduce `s` finché
  `liability ≤ cap` (il profit resterà **sotto** `P`; loggato). Default **off**.

---

## 3. Selezione del risultato esatto (score selection)

Per il mercato `CORRECT_SCORE` del match, tra i runner con `availableToLay`:

1. **Filtra per quota**: tieni solo i runner con miglior quota lay `O` tale che
   `price_min ≤ O ≤ price_max` (default **[20, 120]**).
2. **Filtra liquidità**: `availableToLay.size ≥ min_lay_liquidity` (default **5 €**).
3. **Filtra tipologia**: solo scoreline numeriche `H - A` se `include_aggregate =
   false` (default). Gli aggregati «Any Other …» sono esclusi di default.
4. **Scegli il meno probabile**: tra i superstiti, prendi quello con **quota lay
   più ALTA** (probabilità minima). Tie-break: liquidità maggiore, poi liability
   minore.
5. Se nessun runner supera i filtri → **salta il match** (I6), logga `skip`.

> Nota: il mercato Correct Score si ri-prezza da solo con il punteggio live e
> **sospende i punteggi diventati impossibili** (es. a 2-0 il runner "1-0" sparisce):
> la regola «quota più alta nel range» si adatta automaticamente senza che Omega
> debba conoscere il punteggio. Il feed punteggio (§5) serve solo al **gating del
> minuto** e alla telemetria, non alla selezione.

---

## 4. Finestra di ingresso (timing)

Omega piazza su un match **solo** quando è nella sua fascia in corso, così da non
immobilizzare liquidità su partite che partono tra ore.

Un match è **eleggibile** quando **tutte** valgono:
- il suo mercato `CORRECT_SCORE` è **OPEN** e **in-play** (`inplay = true`);
- il **minuto** ∈ `[entry_minute_min, entry_minute_max]` (default **[30, 60]**),
  dove il minuto viene da:
  - `entry_window_source = 'score'` (default): minuto del feed punteggio (§5);
  - `entry_window_source = 'clock'`: minuti trascorsi da `marketStartTime`
    (fallback quando il feed non è disponibile);
- non è già stato piazzato (I1);
- `marketStartTime` cade **oggi** (universo giornaliero);
- se `max_events > 0`: numero di match già piazzati `< max_events`.

L'universo giornaliero si ottiene con `list_events(["1"], from=now−12h, to=fine
giornata)` per includere anche i match **già iniziati** (il loro `marketStartTime`
è nel passato).

---

## 5. Minuto+punteggio live — CONDIVISI dal runner calcio (via `live_now`)

Omega **NON apre una seconda sessione Betfair** per il punteggio: legge minuto e
punteggio dalla tabella **condivisa `live_now`** (scritta dal runner calcio ogni
~5s tramite `ScorePoller`/`BetfairInPlayProvider`), ESATTAMENTE come lo scalper
(`scalper_session.py:451-514`). Pura lettura Supabase (`omega_db.read_live_now`),
join diretto per `event_id` Betfair (stesso spazio ID → nessun matching). Usato per:
- gating del minuto (§4) quando `entry_window_source='score'` (default);
- telemetria: `score_at_entry`, `minute_at_entry` salvati sul trade;
- (non usato per la selezione — vedi §3).

**Guardia freschezza** (che lo scalper NON ha): se `live_now.updated_at` è più
vecchio di `SCORE_MAX_AGE_S` (180s), il dato è considerato congelato → Omega
degrada al `clock`. **Copertura**: `live_now` contiene una riga solo per gli
eventi SEGUITI dal runner (`live_follow` ← `personal_watchlist`); per i match non
seguiti Omega usa il `clock` (`marketStartTime`), senza mai fermarsi (I6).

---

## 6. Ciclo di vita di un trade

```
(match entra in finestra) → SELECT score → SIZE → PLACE lay
   PAPER: fill simulato al best-lay live, size ≤ liquidità disponibile
   LIVE : client.place_orders(side=LAY, customerRef=omega-<event_id>)
→ status = 'open' (liability impegnata)
→ (fine match) settlement del mercato CORRECT_SCORE:
   runner nostro = WINNER → status='lost',  pnl = −liability
   runner nostro = LOSER  → status='won',   pnl = +s·(1−c)
   mercato VOID/abbandonato → status='void', pnl = 0
→ scrittura su omega_trades + omega_activity + aggiornamento stats/equity
```

- **PAPER fill model**: si assume il match al **best lay price** live per una size
  ≤ `availableToLay.size` a quel prezzo. Se la size target eccede la liquidità al
  best, si cammina la ladder (prezzi lay peggiori) o si riduce la size (loggato).
  Modello onesto per la validazione; il LIVE userà i fill reali riconciliati.
- **Settlement PAPER**: si polla il market book della CS finché `status='CLOSED'`,
  poi si leggono gli stati runner (`WINNER`/`LOSER`). Autorevole quanto il LIVE.

---

## 7. Parametri configurabili dalla UI

Colonne dedicate su `omega_control`: `daily_goal`, `mode` (`paper|live`),
`status`, più `params JSONB` con **whitelist doppia** (frontend `OMEGA_PARAM_*` ↔
backend `OMEGA_VALIDATED_PARAMS`). Chiavi e default:

| chiave | default | significato |
|---|---:|---|
| `price_min` | 20 | quota lay minima |
| `price_max` | 120 | quota lay massima ("non 600") |
| `entry_minute_min` | 30 | minuto minimo d'ingresso |
| `entry_minute_max` | 60 | minuto massimo d'ingresso |
| `max_events` | 0 | tetto match/giorno (0 = illimitato) |
| `commission_pct` | 5.0 | commissione Betfair |
| `min_lay_liquidity` | 5 | size lay minima al best |
| `min_stake` | 0.50 | stake lay minimo .it |
| `include_aggregate` | false | includere runner "Any Other …" |
| `stop_on_goal` | true | stop nuovi ingressi a obiettivo raggiunto |
| `entry_window_source` | "score" | `score` (minuto+punteggio da `live_now` CONDIVISO col runner, guardia freschezza; fallback clock per match non seguiti) \| `clock` (minuto da `marketStartTime`) |
| `poll_interval_s` | 20 | cadenza del loop |
| `max_liability_per_match` | 0 | cap liability/match (0 = off) |
| `daily_loss_cap` | 0 | stop-loss giornaliero (0 = off) |
| `max_open_liability` | 0 | cap liability aperta totale (0 = off) |

> Scelta utente 11/07: **set-and-forget senza limiti** → i tre cap
> (`max_liability_per_match`, `daily_loss_cap`, `max_open_liability`) sono
> **presenti ma default OFF (=0)**; l'utente li accende quando vuole (punto 5 del
> goal). Quando `> 0` sono **realmente applicati** nel loop:
> `max_liability_per_match` riduce la size; `max_open_liability` blocca l'ingresso
> se la liability aperta lo supererebbe; `daily_loss_cap` ferma i **nuovi** ingressi
> quando il P&L realizzato scende sotto `−cap` (i trade aperti si regolano comunque).
> La commissione è **fissata sul trade al piazzamento**: cambiarla a caldo non
> altera il P&L dei trade già aperti.

---

## 8. Architettura & DB (DB-as-bus, come scalper/tennis)

```
UI React (/omega)  ──RPC owner-only──►  Supabase (omega_control, omega_trades, omega_activity)
      ▲  realtime/polling                         ▲  service_role
      └───────────────────────────────  omega_service.py (loop locale)
                                          ├─ omega_market.py  (Betfair REST: events/catalogue/book/place)
                                          ├─ omega_engine.py  (LOGICA PURA: selezione/sizing/target/settlement) ← TESTATA
                                          ├─ omega_paper.py   (motore simulazione PAPER)
                                          └─ omega_db.py      (I/O Supabase)
```
- **Backend**: `Betfair/omega/` — supervisore singolo (una `omega_control`
  "singleton", non per-evento). Riusa `odds_refresh.get_shared_client()`
  (sessione Betfair condivisa), `db_client.get_supabase_client()`,
  `live_order_build.{lay_size_from_liability, min_stake_rules}`, `scores/`.
- **DB**: `migrations/omega_bot.sql` — `omega_control` (singleton) + `omega_trades`
  (mirror append/update) + `omega_activity` (log) + RPC `omega_activate` /
  `omega_stop` / `omega_update_params` / `get_omega_state` / `get_omega_trades`.
  `omega_control` e `omega_trades` in **realtime publication** per la dashboard.
- **Frontend**: `frontend/src/lib/omega.ts` (client RPC + tipi + whitelist),
  route `/omega` (App.tsx), card in `SelectSport`, pagina fullscreen
  `pages/Omega.tsx` (equity curve, barra obiettivo, lista trade live, popup incassi
  via `sonner`, pannello parametri, START/STOP + toggle PAPER/LIVE).

**Avvio locale**: `python -m Betfair.omega.omega_service`
(+ `.bat` dedicato e voce in `desktop/main.js`).

---

## 9. Onestà sul rischio (da mostrare, non nascondere — I8)

La strategia LAY su risultato esatto **poco probabile** è, a quote **fair**,
**EV ≈ 0** (leggermente negativo per commissione + overround): non esiste edge
meccanico (coerente con le ricerche precedenti del progetto). Profilo:
- vinci `≈ P` con probabilità alta (~98–99% per match);
- perdi `≈ liability` (grande, es. €300–500/match a quota 100) con probabilità
  bassa (~1–2%).

**Conseguenza**: la maggior parte dei giorni chiude **+€250**, ma la varianza è a
**coda pesante** — un singolo risultato che colpisce può bruciare **giorni o
settimane** di profitti. Omega implementa **fedelmente** questa strategia perché
richiesta, ma la dashboard espone sempre **liability aperta** e **drawdown**, e i
tre cap del §7 sono a un click di distanza. Questa sezione è parte della
Costituzione: nessuna versione di Omega può rimuoverla o mascherare il rischio.

---

## 10. Definition of Done

- [ ] `omega_engine` puro con **test pytest** (selezione, sizing, target dinamico,
      settlement, idempotenza, finestra) verdi, ≥80% copertura del modulo.
- [ ] Migrazione `omega_bot.sql` idempotente (tabelle + 5 RPC owner-only + realtime).
- [ ] `omega_service` gira in **PAPER** end-to-end su eventi reali senza errori,
      piazza ≤1 trade/match, aggiorna stato/equity, regola il P&L al settlement.
- [ ] Frontend: card Omega → `/omega` fullscreen; equity real-time, barra
      obiettivo, lista trade, popup incassi, pannello parametri, START/STOP,
      toggle PAPER/LIVE. Test vitest della pagina + `lib/omega.ts` verdi.
- [ ] `npm run build` (tsc) e `pytest` verdi. Nessun `print()` nel codice runtime
      (usare `logging`).
- [ ] **Review approfondita finale** (punto 6 del goal): code-review + security +
      verifica manuale del flusso PAPER.
- [ ] LIVE **non** attivato senza semaforo esplicito dell'utente.

---

_«Omega piazza una scommessa e aspetta. La disciplina è nel non fare altro.»_
