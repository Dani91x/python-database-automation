"""Betfair Stream API live + storico per Match Replay.

Vedi Betfair/PIANO_STREAM_LIVE.md per l'architettura completa.

Layer:
  - auth            : APIClient betfairlightweight (cert login .it)
  - recorder        : flumine MarketRecorder (firehose grezzo nativo, locale)
  - scores/         : ScoreProvider (in-play Betfair primario + API-Football fallback)
  - curator         : file grezzo -> snapshot curati (write-on-change)
  - uploader        : upsert idempotente su Supabase
  - engine/         : motore live (ricalcolo prob in-match)
  - runner          : orchestratore long-running
"""
