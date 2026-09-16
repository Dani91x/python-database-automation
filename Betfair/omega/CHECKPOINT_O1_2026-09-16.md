# CHECKPOINT O1 — Omega: «se chiudo io, il bot deve saperlo» (16/09/2026, sera)

Delegato O1 (Opus 5). Repo `master`, pushato fino a `740fad7`. **Nessun commit fatto da me.**

## Ordine dell'utente (16/09 sera) — la fonte
> «se chiudo io (anche fuori dall'app, direttamente su Betfair) il bot deve saperlo e NON
> gestire posizioni che non esistono piu'; cash-out globale -> al controllo dopo non fa
> altro; il bot gestisce le SUE operazioni e ignora le mie manuali».

## I quattro punti — TUTTI CHIUSI
| # | Reperto | Stato |
|---|---------|-------|
| 1 | **R9** chiusura fatta dall'utente SU BETFAIR mai riletta (green-up su posizione inesistente = back con soldi veri) | FATTO |
| 2 | **R8** nessuno stato per evento «chiuso dall'utente» (era un effetto collaterale di `manual_event_ids`) | FATTO |
| 3 | **R6/R7** aggregati che decidono con dentro le manuali; green-up automatico sulle righe manuali | FATTO |
| 4 | Test + falsificazioni + replay (`chiuso-fuori-app`, E5) + suite | FATTO |

## Dove sta ogni cosa — file:riga
| Cosa | Dove |
|------|------|
| `posizione_di_conto(market_id, selection_id=None)` PRODUZIONE | `Betfair/omega/omega_market.py:1280` |
| `posizione_di_conto` BANCO (stesso nome, stessa firma, stesse chiavi) | `Betfair/stream/backtest/banco_comune.py:858` |
| R9 sorveglianza | `omega_service.py:2756` (`sorveglia_posizione_di_conto`), chiamata da `settle_open:2943` |
| R9 aiutanti | `_netto_di_conto:2652` · `_gruppi_di_conto:2686` · `_marca_chiuso_dall_utente:2740` |
| Cadenza della lettura | `omega_config.py:191` → `conto_every_s` (default **120 s**, 0 = ogni giro; per MERCATO+selezione) |
| R8 stato dell'evento (scrittura) | `omega_service.py:2866` (`_chiudi_evento`) · `_dopo_il_cashout:3909` · `chiudi_eventi_in_attesa:3974` |
| R8 stato dell'evento (lettura) | `omega_service.py:2900` (`eventi_chiusi_dall_utente`) · `scan_and_place_legs:971` · `_greenup_candidates:4165` |
| R8 DB | `omega_db.py:396/410/428/450` (`event_user_state`, `set_event_user_state`, `user_closed_event_ids`, `resume_event`) |
| R6 motore | `omega_engine.py:338` (`posizione_manuale`) · `:371` (`aggregate_trades(..., solo_auto=False)`) |
| R6 DB | `omega_db.py:655` (`aggregates_coppia`) · `:752` (`_righe_per_aggregati`) · `:780` (`_esistono_manuali_che_contano`) |
| R6 servizio | `omega_service.py:295` (`_aggregati_cached` → coppia) · `run_once` (`agg_pagina`/`agg`, stats `open_liability_bot`) |
| R7 | `omega_service.py:4165` (`_greenup_candidates` salta manuali / evento chiuso / riga chiusa fuori app) |
| §12 Costituzione aggiornata con la data | `Betfair/omega/COSTITUZIONE_OMEGA.md` §12 (riquadro «MODIFICATO DALL'ORDINE DEL 16/09») |
| Migrazione (NON applicata) | `migrations/omega_chiuso_dall_utente_2026-09-16.sql` (276 righe) |
| Controllo E5 + E3 rifatto | `Betfair/omega/certificazione.py:829` (`_e5`) · `:724` (`_e3`) |
| Scenario `chiuso-fuori-app` | `Betfair/omega/tools/replay_registrazioni.py` (`SCENARI`, `_chiudi_fuori_app`) |
| Test nuovi | `Betfair/omega/test_omega_chiuso_dall_utente_2026_09_16.py` (38) + 7 su E5 in `test_omega_replay_2026_09_16.py` |

## Replay — prima/dopo (misurato, non dedotto)
`python -m Betfair.stream.backtest.certifica omega 35760084 --scenari apertura,manuale-e-bot,cashout-globale,chiuso-fuori-app --worker 3`

| | PRIMA (difetti R6+R7 rimessi) | DOPO |
|---|---|---|
| `manuale-e-bot` | **KO — 466 violazioni E3** | OK — 0 violazioni, E3 x466 |
| 4 scenari insieme | — | **0 violazioni**, E1 x324, E3 x576, E4 x110, **E5 x108** |

## Falsificazione — 11 mutazioni, 11 catturate
R6 (solo_auto ignorato · origin della riga invece che della posizione) · R7 (green-up sulle
manuali) · R8 (apertura cieca allo stato · cash-out che non scrive · chiusura in volo mai
riguardata) · R9 (green-up su posizione chiusa fuori app · conto letto filtrato per strategia ·
regolati ignorati) · E3 e E5 smontati nel controllo.

## Suite
`python -m pytest Betfair/omega Betfair/stream -q -p no:cacheprovider` → **2241 verdi**.

## Cosa serve lato UI (NON fatto: divieto esplicito di toccare il frontend)
1. `frontend/src/lib/omega.ts` — `OMEGA_PARAM_GROUPS`/`OMEGA_PARAM_DEFAULTS`: campo
   **`conto_every_s`** (gruppo «respiro del database», secondi, default 120, 0–3600).
   Fino ad allora e' dichiarato in `_IN_ATTESA_DI_PANNELLO` del test di contratto.
2. `OMEGA_ACTIVITY_EXTRA` / `ACTIVITY_BASE`: etichetta per **`chiuso_dall_utente`**
   (unico kind nuovo; dichiarato in `_KIND_IN_ATTESA_DI_UI`). Tutto il resto usa kind che
   esistono gia' (`skip`, `diagnosi`, `error`, `schema_warn`).
3. Pulsante **«Riprendi»** sulla partita → RPC `omega_evento_riprendi(event_id)`; elenco da
   `omega_eventi_chiusi_dall_utente()`. Senza, lo stato si toglie solo da SQL.
4. Testata: affiancare `open_liability` (conto) e `open_liability_bot` (su cui il bot decide).

## Limiti dichiarati (⊘)
- La migrazione NON e' applicata: finche' non lo e', lo stato dell'evento vive in RAM e si
  perde al riavvio (il servizio lo dichiara con `schema_warn`).
- Gli ordini del bot ancora VIVI su una partita chiusa dall'utente vengono ELENCATI, non
  annullati (scelta: nessuna azione di iniziativa sugli ordini).
- Il gesto «Riprendi» fatto da un altro processo si vede entro `sets_cache_s` (30 s).
- Lo scenario `chiuso-fuori-app` gira su UNA partita: il caso multi-evento resta ⊘.
- `posizione_di_conto` non e' mai stata provata contro Betfair vero (solo banco e finti).
