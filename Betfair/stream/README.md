# Betfair Stream Live — guida operativa

Sistema live + storico per Match Replay. Architettura completa: `Betfair/PIANO_STREAM_LIVE.md`.

## Setup (una volta)
1. `pip install -r requirements.txt` (porta `flumine` + `betfairlightweight`).
2. Applicare le migrazioni nel **Supabase SQL Editor** (ordine):
   - `migrations/live_stream.sql`
   - `migrations/live_stream_rpc.sql`
3. `.env` — già presenti `BETFAIR_*`, `API_FOOTBALL_KEY`, `SUPABASE_*`.
   Opzionali (hanno default sensati, vedi `config_stream.py`):
   ```
   LIVE_STREAM_DATA_DIR=./_live_raw
   LIVE_SCORE_POLL_SEC=5
   LIVE_FALLBACK_THRESHOLD=3
   LIVE_FALLBACK_RETRY_PRIMARY_SEC=120
   LIVE_UPLOAD_CADENCE_SEC=10
   LIVE_LADDER_DEPTH=3
   LIVE_STREAM_CONFLATE_MS=0
   ```

## Uso (in locale, durante le partite)
```bash
# aggancia le partite GIOCATA agli eventi Betfair e streamma tutto
python -m Betfair.stream.runner

# oppure: streamma un solo evento già presente in live_follow
python -m Betfair.stream.runner --event 1.234567890
```
Ctrl+C termina lo stream, cura i dati e li carica su Supabase (status → UPLOADED).

Ri-curare/ricaricare una partita dai file locali (idempotente):
```bash
python -m Betfair.stream.uploader <event_id>
```

## Backtest Automatico (FlumineSimulation) — worker locale OBBLIGATORIO
La dashboard "Backtest Automatico" inserisce una richiesta nella coda
`live_backtest_requests` (stato `PENDING`). La simulazione gira in LOCALE via
flumine sui file `.raw.jsonl` registrati: serve quindi un **worker locale sempre
attivo** che consuma la coda. Senza worker la richiesta resta "in coda" all'infinito.

```bash
# avvia il worker e LASCIALO APERTO (sul PC che ha le registrazioni in _live_raw/)
python -m Betfair.stream.backtest.worker

# opzioni: --once (processa 1 richiesta e termina, per test) --log-level DEBUG
python -m Betfair.stream.backtest.worker --once --log-level INFO
```

**Auto-avvio (consigliato):** invece di ricordarsi di lanciarlo, registralo come task
automatico al login di Windows (parte invisibile in background, sempre attivo):
```powershell
# click destro > Esegui con PowerShell  (non serve amministratore)
.\install_worker_autostart.ps1
# per rimuoverlo:
.\install_worker_autostart.ps1 -Uninstall
```
In alternativa, doppio click su `start_backtest_worker.bat` (finestra visibile).
Ciclo di una richiesta: `PENDING` → (worker la prende) `RUNNING` → `DONE` (risultati
in `live_backtest_results`) oppure `ERROR` (motivo in `error_detail`). Le metriche
derivano ESCLUSIVAMENTE dal settlement simulato di flumine.

Modalità:
- **Motore Live (`engine`)**: applica `live_engine_pro` (stessi λ/edge/Kelly del live)
  alle partite registrate. Params: `bankroll`, `min_edge`, `kelly_fraction`.
- **Sandbox (`sandbox`)**: regola meccanica configurabile. Params in `rules`:
  `market_type`, `side` (BACK/LAY), `selection_id`, `entry_minute`,
  `entry_price_max`, `stake`.

**Esecuzione (realismo flumine, entrambe le modalità):**
- `commission_rate` — commissione Betfair (es. 0.05 = 5%), applicata PER MERCATO sul
  netto vincente. Il `total_pnl` risultante è NETTO; `metrics.gross_pnl` e
  `metrics.commission` restano esposti per trasparenza.
- `persistence_type` — sorte dell'inmatchato a fine mercato: `LAPSE` (annulla),
  `PERSIST` (porta in-play), `MARKET_ON_CLOSE` (SP).
- `simulation_available_prices` — matcha anche contro i prezzi disponibili (non solo
  il traded): fill più realistici dell'inmatchato.
- `place_latency` / `cancel_latency` — latenza simulata (secondi). Il **bet delay**
  in-play (~5s nel calcio) è già modellato da flumine dal `marketDefinition`.

## Frontend
- **Segui Live** (`/segui-live`): partite in streaming, aggiornamento real-time via Supabase Realtime su `live_now`.
- **Match Replay** (`/match-replay`): simulatore trading sui dati registrati (tutti i mercati), P&L back/lay.
- **Backtest Automatico**: vedi sezione sopra (richiede il worker locale attivo).

## Flusso dati
```
Betfair Stream ─► recorder (JSONL locale, source of truth)
              └─► worker punteggio (in-play Betfair → fallback API-Football)
                     ├─► live_now  (glance real-time, ~10s)  ─► Segui Live
                     └─► scores JSONL locale
fine partita ─► uploader: curator (write-on-change) ─► live_market_snapshots
                                                    ─► live_score_timeline  ─► Match Replay
```

## Test
```bash
python -m pytest Betfair/stream/tests/ -q
```

## Note di design
- Lo storage real-time NON tocca Supabase (solo `live_now`, 1 riga/partita): vincolo I/O.
- Il punteggio primario è l'in-play Betfair (stessi event_id, no matching); fallback
  API-Football dietro `ScoreProvider` con circuit breaker.
- Estensione futura: registrazione anche nel formato nativo Betfair per il motore di
  replay/simulazione di flumine (oggi si registra il MarketBook parsato in JSONL,
  sufficiente per curazione + simulatore frontend).
