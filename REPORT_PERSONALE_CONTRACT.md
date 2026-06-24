# Contratto di build — Watchlist + Report Personale

> Spec UNICA e vincolante. Ogni agente implementa SOLO ciò che è qui dentro, con
> questi nomi esatti (tabelle, colonne, RPC, tipi, file). Niente deviazioni.
> Obiettivo: tracciare l'operatività reale dell'utente (pre-match + live) con
> **piena tracciabilità** ("risalire a ogni singola cosa") e metriche
> **matematicamente corrette** (certificate oracle==RPC).

## 0. Flusso utente (4 fasi)
1. Dashboard → filtro **Match Betfair** (esiste). Aggiunta: checkbox ☑ per riga + bottone "Aggiungi a Watchlist".
2. **Watchlist**: spuntare una partita → il sistema **congela uno snapshot** completo del pre-match (tutti i motori + quote Betfair + edge + consigli). Stato iniziale `DA_VALUTARE`.
3. Decisione: **GIOCATA** (apre scheda trade, pre-compilata) oppure **SCARTATA** (motivo + nota). Entrambe tracciate.
4. **Report Personale**: KPI + equity curve + breakdown + tabella trade, tutto calcolato lato DB.

Principio chiave: lo snapshot è **server-side e immutabile**. L'utente può uscire dai consigli del sistema; il sistema registra sia il consiglio sia la scelta dell'utente (`followed_advice`).

---

## 1. SCHEMA DB (nuove tabelle — file `migrations/personal_tracking.sql`)

Convenzioni progetto: schema `public`, snake_case, `created_at/updated_at TIMESTAMPTZ default now()`,
RLS ON, `REVOKE ALL FROM anon, authenticated`, accesso SOLO via RPC `SECURITY DEFINER`
con `SET search_path = public, pg_temp`. Le RPC di scrittura sono concesse a
`authenticated, service_role` (l'early-access garantisce che solo l'owner sia autenticato).
Tutte le tabelle: `CREATE TABLE IF NOT EXISTS`. Idempotente.

### 1.1 `personal_watchlist` (1 riga = 1 partita spuntata)
```
id              BIGSERIAL PK
fixture_id      BIGINT NOT NULL
league_id       BIGINT
league_name     TEXT
season_year     SMALLINT
country         TEXT
round           TEXT
home_team       TEXT
away_team       TEXT
kickoff         TIMESTAMPTZ
status          TEXT NOT NULL DEFAULT 'DA_VALUTARE'
                  CHECK (status IN ('DA_VALUTARE','GIOCATA','SCARTATA'))
snapshot        JSONB NOT NULL DEFAULT '{}'::jsonb   -- vedi §1.4
consigli        JSONB NOT NULL DEFAULT '[]'::jsonb    -- top selezioni consigliate (vedi §1.4)
snapshot_at     TIMESTAMPTZ NOT NULL DEFAULT now()
user_note       TEXT
strategia_ipotizzata TEXT
tags            TEXT[] NOT NULL DEFAULT '{}'
reject_reason   TEXT      -- valorizzato se SCARTATA (enum §1.5)
reject_note     TEXT
decided_at      TIMESTAMPTZ
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
UNIQUE (fixture_id)   -- una partita una sola volta in watchlist (riusabile)
```
Indici: `idx_pw_status (status)`, `idx_pw_kickoff (kickoff)`, `idx_pw_fixture (fixture_id)`.

### 1.2 `personal_trades` (1 riga = 1 operazione piazzata)
```
id              BIGSERIAL PK
watchlist_id    BIGINT REFERENCES personal_watchlist(id) ON DELETE SET NULL
-- identità match denormalizzata (per query report senza join)
fixture_id      BIGINT
league_id       BIGINT
league_name     TEXT
home_team       TEXT
away_team       TEXT
kickoff         TIMESTAMPTZ
-- ingresso a mercato
strategia       TEXT NOT NULL
side            TEXT NOT NULL CHECK (side IN ('back','lay'))
market          TEXT
selection       TEXT
line            NUMERIC
entry_odds      NUMERIC NOT NULL CHECK (entry_odds > 1)
stake           NUMERIC NOT NULL CHECK (stake >= 0)   -- backer stake
liability       NUMERIC                               -- per lay = stake*(odds-1)
exit_odds       NUMERIC                               -- cash-out (opz.)
timing          TEXT NOT NULL DEFAULT 'prematch' CHECK (timing IN ('prematch','live'))
entry_minute    SMALLINT
entry_score     TEXT
exchange        TEXT NOT NULL DEFAULT 'Betfair'
commission      NUMERIC NOT NULL DEFAULT 0.05
time_operative_min NUMERIC
-- esito
status          TEXT NOT NULL DEFAULT 'OPEN'
                  CHECK (status IN ('OPEN','WON','LOST','VOID','PARTIAL'))
result_ft       TEXT
gross_pnl       NUMERIC
net_pnl         NUMERIC                                -- "Gain Netto" (entry + legs)
roi             NUMERIC                                -- net_pnl/stake (stored)
hourly_yield    NUMERIC                                -- net_pnl/(time_min/60)
-- contesto congelato dallo snapshot per la selezione scelta (analytics)
edge_at_entry   NUMERIC
model_prob      NUMERIC
implied_prob    NUMERIC
affidabilita    NUMERIC                                -- da get_direction
concordi        SMALLINT
motori_totali   SMALLINT
followed_advice BOOLEAN                                -- la selezione era tra i consigli?
-- meta
comment         TEXT
tags            TEXT[] NOT NULL DEFAULT '{}'
trade_date      DATE NOT NULL                          -- giorno operativo (default kickoff::date)
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
```
Indici: `idx_pt_date (trade_date)`, `idx_pt_status (status)`, `idx_pt_strategia (strategia)`,
`idx_pt_league (league_id)`, `idx_pt_fixture (fixture_id)`, `idx_pt_watchlist (watchlist_id)`.

### 1.3 `personal_trade_legs` (coperture/hedge/cashout aggiuntivi)
```
id          BIGSERIAL PK
trade_id    BIGINT NOT NULL REFERENCES personal_trades(id) ON DELETE CASCADE
leg_type    TEXT NOT NULL CHECK (leg_type IN ('hedge','cashout','coverage','adjust'))
side        TEXT CHECK (side IN ('back','lay'))
market      TEXT
selection   TEXT
odds        NUMERIC
stake       NUMERIC
liability   NUMERIC
timing      TEXT CHECK (timing IN ('prematch','live'))
minute      SMALLINT
net_pnl     NUMERIC
note        TEXT
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
```
Indice: `idx_ptl_trade (trade_id)`. La `net_pnl` del trade = economia entry + Σ leg net_pnl
(ricalcolata da `recompute_personal_trade(trade_id)`; vedi §2.6).

### 1.4 Struttura `snapshot` JSONB (congelata da `add_to_watchlist`)
```json
{
  "generated_at": "ISO ts",
  "direction": <output integrale di get_direction(fixture_id)>,
  "betfair": <output integrale di get_betfair_direction_odds(fixture_id)>,
  "full_odds_markets": ["Match Odds", "..."],   // elenco mercati Betfair disponibili
  "edges": [                                      // 1 per (market,selection consigliata)
    {"market":"over_2_5","selection":"Under","model_prob":0.62,
     "best_back":1.70,"best_lay":1.72,"implied_prob":0.588,
     "edge":0.032,"ev_back":..., "affidabilita":0.61,"lift":0.13,
     "concordi":["poisson","ml"],"motori_totali":4}
  ]
}
```
`consigli` JSONB = sottoinsieme di `edges` ordinato per `edge` decrescente (top N, default 5),
ossia le selezioni che il sistema raccomanda. Serve a calcolare `followed_advice`.

EV (Betfair, commissione su vincita): `ev_back = model_prob*(odds-1)*(1-comm) - (1-model_prob)`.
`edge = model_prob - 1/odds`. `implied_prob = 1/odds`.

### 1.5 Enum motivi di scarto (`reject_reason`)
`quota_bassa`, `edge_insufficiente`, `formazioni`, `infortuni`, `non_mi_fido`,
`troppe_operazioni`, `liquidita_scarsa`, `gestione_rischio`, `altro`.

---

## 2. RPC (file `migrations/personal_tracking_rpc.sql`)
Tutte `SECURITY DEFINER`, `SET search_path = public, pg_temp`.
Lettura: `STABLE`. Scrittura: `VOLATILE`. Whitelisting input come nelle RPC esistenti.
Grant: `REVOKE ALL FROM public; GRANT EXECUTE TO authenticated, service_role;` (MAI anon).

### 2.1 `add_to_watchlist(p_fixture_id bigint) returns jsonb`
- Recupera identità match da `fixture_predictions`.
- Chiama internamente `get_direction(p_fixture_id)` e `get_betfair_direction_odds(p_fixture_id)`.
- Costruisce `snapshot` (§1.4) e `consigli` (top 5 per edge, solo edge>0).
- UPSERT su `personal_watchlist` (UNIQUE fixture_id): se esiste e status='DA_VALUTARE' aggiorna snapshot; altrimenti NON sovrascrive una decisione presa (ritorna la riga esistente).
- Ritorna la riga watchlist completa.

### 2.2 `get_watchlist(p_status text default null) returns jsonb`
- Ritorna array di righe watchlist (filtrabile per status), ordinate per kickoff.
- Include `n_trades` (conteggio trade collegati).

### 2.3 `set_watchlist_decision(p_id bigint, p_status text, p_reject_reason text, p_reject_note text, p_note text, p_strategia text, p_tags text[]) returns jsonb`
- `p_status IN ('GIOCATA','SCARTATA','DA_VALUTARE')`.
- Se SCARTATA: valida `p_reject_reason` ∈ enum §1.5.
- Setta `decided_at = now()`. Ritorna riga aggiornata.

### 2.4 `add_personal_trade(p jsonb) returns jsonb`
- Input JSON con i campi §1.2 (entry). `watchlist_id` opzionale.
- Calcola `liability` se lay e non fornita; `trade_date` default `kickoff::date` o oggi.
- Se `watchlist_id` presente: congela `edge_at_entry/model_prob/implied_prob/affidabilita/concordi/motori_totali` dallo snapshot per `(market,selection)`, e calcola `followed_advice` (selezione presente in `consigli`).
- Se watchlist collegata: porta il suo status a `GIOCATA`.
- Chiama `recompute_personal_trade(new_id)`. Ritorna trade.

### 2.5 `add_trade_leg(p jsonb) returns jsonb` / `settle_personal_trade(p_id bigint, p_status text, p_result_ft text, p_exit_odds numeric, p_time_min numeric) returns jsonb`
- `add_trade_leg`: inserisce leg, poi `recompute_personal_trade`.
- `settle_personal_trade`: setta status finale (WON/LOST/VOID/PARTIAL), result, exit, tempo; `recompute_personal_trade`.

### 2.6 `recompute_personal_trade(p_id bigint) returns void` (interna)
Ricalcola e salva su `personal_trades`:
- `net_pnl`:
  - Se WON: `back` → `stake*(entry_odds-1)*(1-commission)`; `lay` → `stake*(1-commission)`.
  - Se LOST: `back` → `-stake`; `lay` → `-(liability)` (= `-stake*(entry_odds-1)`).
  - VOID → 0. PARTIAL/OPEN → usa `exit_odds` se presente (cash-out): pnl = posizione chiusa a exit.
  - **Più** Σ `net_pnl` dei leg.
- `gross_pnl`: come net ma senza `(1-commission)`.
- `roi = net_pnl/NULLIF(stake,0)`; `hourly_yield = net_pnl/NULLIF(time_operative_min/60,0)`.

### 2.7 `get_personal_report(p_from date, p_to date, p_strategia text, p_league_id int, p_status text) returns jsonb`
Ritorna oggetto con:
- `daily`: array `{day, pnl, equity, peak, drawdown, n_trades}` (serie giornaliera, equity cumulativa da 0).
- `metrics`: tutte le metriche §3.
- `by_strategia`: array `{strategia, n, n_won, win_rate, stake, net_pnl, roi, profit_factor}`.
- `by_league`: idem per lega.
- `advice`: `{n_followed, n_off_advice, roi_followed, roi_off_advice}` (consigli seguiti vs no).
- `discarded`: `{n, by_reason:[{reason,n}]}` (sintesi scartate).
Solo trade `status IN ('WON','LOST','VOID','PARTIAL')` (chiusi) entrano nelle metriche P&L.

### 2.8 `get_personal_trades(p_from date, p_to date, ... , p_limit int) returns jsonb`
Drill-down righe trade con tutti i campi + snapshot-context (edge/affidabilità/concordi).

### 2.9 Lockdown — appendere a `migrations/personal_tracking_rpc.sql`
`revoke execute on function public.<ognuna> from anon;` per TUTTE le RPC sopra.

---

## 3. METRICHE — formule esatte (certificate oracle==RPC)
Serie input = P&L giornaliero `pnl[]` (somma `net_pnl` dei trade chiusi per `trade_date`),
`n = #giorni`. Equity cumulativa `eq[i] = Σ pnl[0..i]` (parte da 0).
**Riproducono l'Excel (validate)**; le 6 di rischio usano definizioni STANDARD (l'Excel usa
normalizzazioni non-standard / alcune celle rotte → si adottano le corrette).

ESATTE vs Excel (confermate al 6° decimale):
- `giorni=n`; `profit_days=#(pnl>0)`; `loss_days=#(pnl<0)`; `pct_profit=profit_days/n*100`
- `tot=Σpnl`; `mean=tot/n`; `max_day=max`; `min_day=min`; `median=mediana`
- `avg_win=mean(pnl>0)`; `avg_loss=mean(pnl<0)`; `wl_ratio=profit_days/loss_days`
- `profit_factor=Σ(pnl>0)/|Σ(pnl<0)|`
- `vol = stdev_campionaria(pnl)` (n-1); `sharpe = mean/vol`
- `kurtosis` = KURT Excel (excess, corretta per campione)
- `pct_top5 = Σ(top5 giorni)/tot`; `pct_worst = min_day/tot`
- operative: `tempo_medio_giorno`, `guadagno_orario_medio`, `profit_per_stake=tot/Σstake`,
  `stake_medio_giorno`, `media_trade_giorno=#trade/n`, `giornate_perdita_gt_stake`

STANDARD (rischio):
- `max_drawdown = min_i(eq[i] - running_peak[i])` (peak-to-trough su equity da 0)
- `recovery_factor = tot/|max_drawdown|`
- `calmar = tot/|max_drawdown|`  (su periodo; senza annualizzazione forzata)
- `ulcer_index = sqrt(mean(DD_pct_i^2))` su TUTTI gli n giorni, con
  `DD_pct_i = (eq[i]-peak_i)/peak_i*100` se `peak_i>0`, altrimenti `0`
  (nessun massimo positivo → drawdown % non definito = 0)
- `upi = mean / ulcer_index`
- `downside_dev = sqrt(mean(min(0,pnl)^2))`; `sortino = mean/downside_dev`
- `cvar_5 = mean(peggior ceil(5%) dei pnl)`
- `max_dd_duration_days` = max #giorni consecutivi sotto un peak precedente
NB doc: i ratio di rischio possono differire dai numeri Excel perché l'Excel non è standard.

---

## 4. FRONTEND

### 4.1 Lib (nuovi file)
`frontend/src/lib/watchlist.ts` — tipi + funzioni:
`addToWatchlist(fixtureId)`, `getWatchlist(status?)`, `setWatchlistDecision(...)`.
`frontend/src/lib/personalReport.ts` — `addPersonalTrade(payload)`, `addTradeLeg(payload)`,
`settlePersonalTrade(...)`, `getPersonalReport(filters)`, `getPersonalTrades(filters)`.
Pattern identico ai lib esistenti: `supabase.rpc('<name>', {...})`, `if(error) throw`.
Esportare interfacce TS per ogni struttura (WatchlistRow, PersonalTrade, ReportData, DailyPoint, Metrics, ...).

### 4.2 UI — design system (OBBLIGATORIO usarlo)
shadcn/ui (`@/components/ui/*`), Tailwind, classi `glass-card`, font `font-display`/`font-heading`,
token colore: `--primary` (emerald) positivo/home, `--secondary`/amber Betfair/away,
`--destructive`/red negativo. Recharts per i grafici. `framer-motion` per animazioni. `sonner` per toast.
Navbar/footer/grid-pattern come Dashboard. ProtectedRoute owner-only.

Componenti nuovi:
- `components/dashboard/WatchlistButton.tsx` — checkbox per riga in MatchesList + bottone
  "Aggiungi a Watchlist (N)" (stile amber come "Match Betfair").
- `components/watchlist/WatchlistPanel.tsx` o pagina — lista card con snapshot (motori, quote,
  edge, consigli evidenziati), badge stato, azioni GIOCATA/SCARTATA (Dialog).
- `components/watchlist/TradeForm.tsx` — Dialog scheda trade pre-compilata (campi §1.2 + legs).
- `pages/ReportPersonale.tsx` — pagina con: KPI cards, equity curve (Recharts LineChart),
  underwater/drawdown, breakdown per strategia/lega (tabelle), heatmap-calendario, consigli vs scelte,
  tabella trade con drill-down → scheda + segnali snapshot.
- `pages/Watchlist.tsx` — pagina watchlist (tab Da valutare/Giocate/Scartate) + analisi scartate.

### 4.3 Wiring (edit a file condivisi — UN SOLO agente, in sequenza)
- `App.tsx`: route `/watchlist` e `/report-personale` (dentro ProtectedRoute).
- `Dashboard.tsx` navbar: bottoni link a Watchlist e Report Personale.
- `MatchesList.tsx`: aggiungere checkbox di selezione + barra "Aggiungi a Watchlist".

### 4.4 UX chiarezza
Ogni passaggio etichettato in italiano, badge stato a colori, tooltip su metriche,
empty-state ("Nessuna partita in watchlist"), conferme su azioni, loading skeleton.

---

## 5. CERTIFICAZIONE (file `_certify_personal_report.py`)
Pattern dei `_certify_*.py` esistenti: oracolo Python vs RPC, **0 mismatch tollerati**.
- Inserisce un dataset di trade sintetici (o usa la serie reale dell'Excel come fixture P&L).
- Calcola le metriche §3 in Python (oracolo già validato sull'Excel: 18/24 esatte).
- Chiama `get_personal_report` e confronta campo-per-campo (tol 1e-6 sui numerici).
- Verifica `recompute_personal_trade` (back/lay, win/lose/void, commissione, legs) con casi noti.
- Stampa OK/MISMATCH per ogni metrica; exit !=0 se mismatch.
NB: l'oracolo P&L è già in `scratchpad/oracle.py` e riproduce l'Excel.

## 6. Definition of Done
- SQL idempotente, RLS+lockdown, RPC owner-only.
- `npm run build` (vite/tsc) verde nel frontend.
- Certificazione math passa (oracle==RPC) — o, se DB non raggiungibile, oracolo Python verde
  e RPC ispezionata a mano contro le formule §3.
- Design coerente, IT, passaggi chiari.
- /code-review approfondita superata; poi commit + push.
