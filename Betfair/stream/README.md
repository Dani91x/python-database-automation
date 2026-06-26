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

## Frontend
- **Segui Live** (`/segui-live`): partite in streaming, aggiornamento real-time via Supabase Realtime su `live_now`.
- **Match Replay** (`/match-replay`): simulatore trading sui dati registrati (tutti i mercati), P&L back/lay.

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
