# Riferimenti mike e Safe calcio su 1ac69d0 (cloud, 08/10/2026)

Commit: `1ac69d0` (branch `claude/blissful-sagan-hri7o6-rif-mike`). Ambiente: container cloud Linux, **nproc = 4**.
Registrazioni: `registrazioni_banco/` decompresse in `_live_raw/` con lo script di `registrazioni_banco/LEGGIMI.md`.
Comando per ogni lancio: `python -m Betfair.stream.backtest.certifica <bot> <evento> --scenari tutti --worker 1`.
8 lanci in parallelo, 4 alla volta (`xargs -P 4`): i tempi sono quindi gonfiati dalla contesa sulla CPU.
Bot Safe calcio dal `--elenco`: `safe_base`, `safe_esatto`, `safe_punta`.

| Bot | Evento | ESITO | Scenari KO | TEMPO TOTALE (referto) | rc |
|---|---|---|---|---|---|
| mike | 35760084 | 26 partite senza violazioni, 0 con violazioni, 0 senza decisioni | nessuno | 10m42.0s (642.0 s), LENTO (oltre 600 s) | 0 |
| mike | 35797769 | 26 partite senza violazioni, 0 con violazioni, 0 senza decisioni | nessuno | 31m56.8s (1916.8 s), LENTO | 0 |
| safe_base | 35760084 | 22 partite senza violazioni, 0 con violazioni, 0 senza decisioni | nessuno | 7m06.1s (426.1 s) | 0 |
| safe_base | 35797769 | 22 partite senza violazioni, 0 con violazioni, 0 senza decisioni | nessuno | 23m42.0s (1422.0 s), LENTO | 0 |
| safe_esatto | 35760084 | 22 partite senza violazioni, 0 con violazioni, 0 senza decisioni | nessuno | 6m56.3s (416.3 s) | 0 |
| safe_esatto | 35797769 | 22 partite senza violazioni, 0 con violazioni, 0 senza decisioni | nessuno | 23m46.3s (1426.3 s), LENTO | 0 |
| safe_punta | 35760084 | 22 partite senza violazioni, 0 con violazioni, 0 senza decisioni | nessuno | 7m03.6s (423.6 s) | 0 |
| safe_punta | 35797769 | 22 partite senza violazioni, 0 con violazioni, 0 senza decisioni | nessuno | 23m35.1s (1415.1 s), LENTO | 0 |

Tempo a parete dell'intero lotto (8 lanci, 4 in parallelo): 2687 s (44m47s).

Note:
- Nessun controllo violato in nessun lancio.
- «LENTO» e' l'avviso del banco (tetto `CERTIFICA_TETTO_S` = 600 s): non cambia l'esito. Scenari piu' cari
  su 35797769: mike `punteggio-ko` 78.6 s, safe_base `chiusura-abbinata-in-parte` 70.7 s,
  safe_esatto `proposta-anomalia-effimera` 69.2 s, safe_punta `combos-gamba-automatica` 68.5 s.
  I tempi sono misurati con 4 processi concorrenti su 4 CPU: non sono confrontabili con un lancio singolo.
- Gli stderr (`.err`) contengono solo avvisi di log attesi dagli scenari (es. `MARKET_VALIDATION Market is not open`,
  lay rifiutata EXPIRED in mike, arrotondamento stake Safe), nessun Traceback.
