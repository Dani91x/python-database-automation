# Suite complete in cloud - 08/10/2026

- **sha**: `d0cf8b9482e1a81bf04a9854e48275456f598443` (d0cf8b94, presente: nessun ripiego sulla cima)
- **nproc**: 4 (Linux, container cloud; uptime all'avvio delle suite circa 10 minuti)
- Le quattro suite girate IN PARALLELO, poi la build da sola. Nessuna modifica al codice.

| Suite | Esito | Tempo |
|---|---|---|
| `pytest Betfair/` | **4 failed, 11077 passed, 87 skipped, 6 xfailed**, 14 warnings (exit 1) | 414 s (pytest: 408.64 s) |
| `pytest tools/` | **17 passed** (exit 0) | 108 s |
| `tsc -p tsconfig.app.json --noEmit` | **0 errori** (exit 0) | 88 s |
| `vitest run` | **367 file passed, 10 skipped (377); 5447 test passed, 51 skipped (5498)** (exit 0) | 463 s |
| `npm run build` | **ok** (exit 0; solo l'avviso sui chunk > 1600 kB) | 24 s |

## Rossi e rilancio singolo

Tutti e 4 nello stesso file `Betfair/stream/tests/test_stream_heartbeat_stall_2026_07_17.py`:

- `test_fresh_heartbeats_but_data_beyond_hard_cap_restarts`
- `test_dead_stream_stale_heartbeats_restarts`
- `test_dead_stream_no_heartbeat_info_restarts`
- `test_stall_restart_toctou_recheck_blocks`

**Rilancio del file da solo: ROSSI ANCHE DA SOLI** (4 failed, 12 passed in 0.20 s,
`rilancio_heartbeat_stall.txt`). Quindi NON dipendono dal carico della suite parallela.

### Causa (diagnosi, nessun codice toccato)

Dipende dall'ambiente: il test confronta con l'orologio monotonico, che parte
dall'accensione della macchina. `_stall_env` imposta `R._RAW_STALL_LAST_RESTART = 0.0`;
`stall_restart_due` (`Betfair/stream/runner_lifecycle.py:151`) ammette il restart solo se
`now_monotonic - 0.0 >= _RAW_STALL_RESTART_MIN_INTERVAL_SEC` (default 900 s,
`Betfair/stream/runner.py:1308`). Nel container `time.monotonic()` valeva circa 690-710 s
(= uptime): il throttle blocca il restart, quindi `restart_requested` resta False e il
doppio check TOCTOU non viene mai raggiunto (`calls["n"] == 0`).

Controprova (`rilancio_heartbeat_stall_controprova.txt`, monotonic = 709.8 s):
- con `LIVE_RAW_STALL_RESTART_MIN_INTERVAL_SEC=100` -> **16 passed**;
- con il default 900 -> di nuovo **4 failed, 12 passed**.

Conclusione: il difetto sta nel **test** (presuppone che la macchina sia accesa da più di 15
minuti), non nel codice di produzione. Su una macchina accesa da oltre 900 s passano
(per questo restano verdi sulla postazione dell'utente). Fix suggerito, da decidere al
coordinatore: in `_stall_env` impostare
`_RAW_STALL_LAST_RESTART = _time.monotonic() - 10_000` (stesso schema già usato per
`stream_started_monotonic`), al posto di `0.0`.

## File

`pytest_betfair.txt`, `pytest_tools.txt`, `tsc.txt`, `vitest.txt`, `build.txt`, `tempi.txt`,
`rilancio_heartbeat_stall.txt`, `rilancio_heartbeat_stall_controprova.txt` (tutti < 1 MB, interi).
